import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const viewports = [[320, 640], [360, 780], [390, 844], [414, 896], [768, 1024], [844, 390]];
const root = fileURLToPath(new URL("../", import.meta.url));
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const evidence = resolve(process.env.MOBILE_EVIDENCE_DIR ?? join(root, "evidence"));
const output = resolve(process.env.MOBILE_ARTIFACTS ?? join(root, "mobile-check-screenshots", stamp));

function browserPath() {
  if (process.env.CHROME) return process.env.CHROME;
  const programFiles = [process.env.ProgramFiles, process.env["ProgramFiles(x86)"]].filter(Boolean);
  const windows = [
    ...programFiles.map((dir) => join(dir, "Google", "Chrome", "Application", "chrome.exe")),
  ];
  const paths = (process.env.PATH ?? "").split(delimiter).filter(Boolean);
  const names = ["google-chrome", "chromium", "chromium-browser", "chrome.exe"];
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  return [...paths.flatMap((dir) => names.map((name) => join(dir, name))), ...windows, mac]
    .find(existsSync);
}

async function waitFor(check, label, timeout = 15000) {
  const deadline = Date.now() + timeout;
  do {
    const result = await check();
    if (result) return result;
    await delay(100);
  } while (Date.now() < deadline);
  throw new Error(`Timed out waiting for ${label}`);
}

async function connect(url) {
  const socket = new WebSocket(url);
  const pending = new Map();
  const listeners = new Map();
  let nextId = 0;
  socket.addEventListener("message", ({ data }) => {
    const { id, result, error, sessionId, method, params } = JSON.parse(data);
    if (method) listeners.get(sessionId)?.(method, params);
    const request = pending.get(id);
    if (!request) return;
    pending.delete(id);
    clearTimeout(request.timer);
    if (error) request.reject(new Error(`${request.method}: ${error.message}`));
    else request.resolve(result);
  });
  socket.addEventListener("close", () => {
    for (const request of pending.values()) {
      clearTimeout(request.timer);
      request.reject(new Error(`DevTools disconnected during ${request.method}`));
    }
    pending.clear();
  });
  try {
    await waitFor(() => {
      if (socket.readyState >= WebSocket.CLOSING) throw new Error("DevTools connection closed");
      return socket.readyState === WebSocket.OPEN;
    }, "DevTools connection");
  } catch (error) {
    socket.close();
    throw error;
  }
  return {
    close: () => socket.close(),
    listen(sessionId, callback) {
      if (callback) listeners.set(sessionId, callback);
      else listeners.delete(sessionId);
    },
    call(method, params = {}, sessionId) {
      return new Promise((resolve, reject) => {
        const id = ++nextId;
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new Error(`Timed out during ${method}`));
        }, 15000);
        pending.set(id, { method, resolve, reject, timer });
        socket.send(JSON.stringify({ id, method, params, sessionId }));
      });
    },
  };
}

// Executed inside the page. Check the whole document, including content below the fold.
function inspectPage(width) {
  const issues = [];
  const scrollWidth = document.documentElement.scrollWidth;
  function selector(el) {
    return el.localName + (el.id ? `#${el.id}` : "") + [...el.classList].map((item) => `.${item}`).join("");
  }
  if (innerWidth !== width || scrollWidth > innerWidth) {
    const overflowing = [...document.body.querySelectorAll("*")]
      .filter((el) => el.getBoundingClientRect().right > Math.min(innerWidth, width) + 1)
      .slice(0, 5);
    issues.push({
      area: overflowing[0]?.closest("section[id], header[id]")?.id ?? "overflow",
      message: `expected width ${width}px, innerWidth ${innerWidth}px, scrollWidth ${scrollWidth}px; first offenders: ${overflowing.map(selector).join(", ") || "none"}`,
    });
  }

  function visible(el) {
    if (el.closest("[hidden], [inert], [aria-hidden='true']")) return false;
    const css = getComputedStyle(el);
    return css.visibility === "visible" && el.getClientRects().length > 0
      && css.clipPath === "none";
  }
  function report(el, message) {
    const label = el.getAttribute("aria-label") ?? el.textContent.trim();
    const section = el.closest("section[id], header[id]");
    const area = section?.id ?? (el.closest("footer") ? "footer" : el.closest("nav") ? "nav" : "page");
    const name = `${selector(el)}${label ? ` (${label.replace(/\s+/g, " ").slice(0, 72)})` : ""}`;
    issues.push({ area, message: `${name}: ${message}` });
  }

  const targets = document.querySelectorAll(
    "a[href], button, input:not([type='hidden']), select, textarea, summary, [role='button'], video",
  );
  for (const el of targets) {
    if (!visible(el) || el.matches(":disabled")) continue;
    if (el.matches("a") && getComputedStyle(el).display === "inline" && el.closest("p, li")) continue;
    const rects = [...el.getClientRects()];
    if (rects.some((rect) => rect.width >= 44 && rect.height >= 44)) continue;
    const rect = el.getBoundingClientRect();
    report(el, `tap target ${rect.width.toFixed(1)}x${rect.height.toFixed(1)}px (44x44 minimum)`);
  }

  const text = "main p, main li, section p, section li, header p, header li, "
    + "label, figcaption, caption, code, pre, input, select, textarea";
  for (const el of document.querySelectorAll(text)) {
    if (!visible(el)) continue;
    const min = el.matches("p, li, input, select, textarea") ? 16 : 12;
    const size = parseFloat(getComputedStyle(el).fontSize);
    if (size < min) report(el, `text ${size}px (${min} minimum)`);
  }
  return issues;
}

async function checkPage(cdp, origin, page, width, height) {
  const { targetId } = await cdp.call("Target.createTarget", { url: "about:blank" });
  let sessionId;
  try {
    ({ sessionId } = await cdp.call("Target.attachToTarget", { targetId, flatten: true }));
    const call = (method, params) => cdp.call(method, params, sessionId);
    const errors = new Set();
    cdp.listen(sessionId, (method, params) => {
      if (method === "Runtime.exceptionThrown") {
        const { text, exception } = params.exceptionDetails;
        errors.add(exception?.description?.split("\n")[0] ?? text);
      }
      if (method === "Runtime.consoleAPICalled" && params.type === "error") {
        errors.add(params.args.map((arg) => arg.value ?? arg.description ?? arg.type).join(" "));
      }
    });
    await call("Runtime.enable");
    await call("Network.enable");
    await call("Network.setBlockedURLs", { urls: ["https://fonts.googleapis.com/*", "https://fonts.gstatic.com/*"] });
    await call("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 2, mobile: true,
      screenOrientation: { type: width > height ? "landscapePrimary" : "portraitPrimary", angle: width > height ? 90 : 0 },
    });
    await call("Emulation.setTouchEmulationEnabled", { enabled: true });
    const url = `${origin}/${page}`;
    const { errorText } = await call("Page.navigate", { url });
    if (errorText) throw new Error(`${page}: ${errorText}`);
    async function evaluate(expression) {
      const { result, exceptionDetails } = await call("Runtime.evaluate", {
        expression, returnByValue: true, awaitPromise: true,
      });
      if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
      return result.value;
    }
    await waitFor(
      () => evaluate(`location.href === ${JSON.stringify(url)} && document.readyState === "complete"`),
      `${page} to load`,
    );
    const frame = "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))";
    await evaluate(`document.fonts.ready.then(() => ${frame})`);
    await evaluate(`(async () => {
      for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight) {
        scrollTo({ top: y, behavior: "instant" });
        await ${frame};
      }
      scrollTo({ top: 0, behavior: "instant" });
      await ${frame};
    })()`);
    const issues = await evaluate(`(${inspectPage})(${width})`);
    const sections = await evaluate("Array.from(document.querySelectorAll('header[id], section[id], footer[id]'), el => el.id)");
    for (const id of ["viewport", ...sections]) {
      await evaluate(`(async () => {
        const el = document.getElementById(${JSON.stringify(id)});
        if (el) el.scrollIntoView({ behavior: "instant" });
        else scrollTo({ top: 0, behavior: "instant" });
        await ${frame};
      })()`);
      const { data } = await call("Page.captureScreenshot", { format: "png", optimizeForSpeed: true });
      await writeFile(join(output, `${page.slice(0, -5)}-${width}x${height}-${id}.png`), Buffer.from(data, "base64"));
    }
    return [...issues, ...[...errors].map((message) => ({ area: "console", message }))];
  } finally {
    if (sessionId) cdp.listen(sessionId);
    await cdp.call("Target.closeTarget", { targetId });
  }
}

async function run() {
  await mkdir(output, { recursive: true });
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(join(tmpdir(), "flipside-mobile-"));
  const lines = [];
  const cases = [];
  let child;
  let server;
  let cdp;
  try {
    const executable = browserPath();
    if (!executable) throw new Error("Set CHROME to an installed Chromium or Chrome binary.");
    let serverOutput = "";
    let serverError;
    server = spawn(process.env.PYTHON ?? "python", [
      "-u", "-m", "http.server", "0", "--bind", "127.0.0.1", "--directory", join(root, "site"),
    ], { stdio: ["ignore", "pipe", "ignore"], windowsHide: true });
    server.on("error", (error) => { serverError = error; });
    server.stdout.setEncoding("utf8").on("data", (text) => { serverOutput += text; });
    const httpPort = await waitFor(() => {
      if (serverError) throw serverError;
      if (server.exitCode !== null) throw new Error(`HTTP server exited with status ${server.exitCode}`);
      return /Serving HTTP on 127\.0\.0\.1 port (\d+)/.exec(serverOutput)?.[1];
    }, "loopback HTTP server");
    let launchError;
    child = spawn(executable, [
      "--headless=new", "--no-first-run", "--disable-background-networking", "--disable-dev-shm-usage",
      "--enable-unsafe-swiftshader",
      "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
      `--user-data-dir=${profile}`, "about:blank",
    ], { stdio: "ignore", windowsHide: true });
    child.on("error", (error) => { launchError = error; });
    const [port, path] = await waitFor(async () => {
      if (launchError) throw launchError;
      if (child.exitCode !== null) {
        throw new Error(`Browser exited with status ${child.exitCode}. Check the CHROME binary.`);
      }
      const ready = await readFile(join(profile, "DevToolsActivePort"), "utf8").catch((error) => {
        if (error.code !== "ENOENT") throw error;
        return "";
      });
      const fields = ready.trim().split(/\r?\n/);
      return fields.length === 2 ? fields : null;
    }, "browser startup");
    cdp = await connect(`ws://127.0.0.1:${port}${path}`);
    const { product } = await cdp.call("Browser.getVersion");
    lines.push(`${product} | touch emulation | DPR 2 | CSS pixels | offline font fallback`);
    let failed = 0;
    for (const page of ["index.html", "verify.html"]) {
      for (const [width, height] of viewports) {
        const issues = await checkPage(cdp, `http://127.0.0.1:${httpPort}`, page, width, height);
        cases.push({ page, width, height, issues });
        if (issues.length) failed++;
        const label = `${issues.length ? "FAIL" : "PASS"} ${page} ${width}x${height} (${issues.length} issues)`;
        lines.push(label, ...issues.map(({ area, message }) => `  [${area}] ${message}`));
        console.log(label);
      }
    }
    lines.push(`RESULT ${failed ? "FAIL" : "PASS"} ${12 - failed}/12 page-viewports`);
    process.exitCode = failed ? 1 : 0;
  } catch (error) {
    lines.push(`ERROR ${error.message}`);
    process.exitCode = 2;
  } finally {
    server?.kill();
    if (child?.pid && child.exitCode === null) {
      const exited = new Promise((resolve) => child.once("exit", resolve));
      if (cdp) await Promise.race([cdp.call("Browser.close").catch(() => {}), delay(1000)]);
      await Promise.race([exited, delay(2000)]);
      if (child.exitCode === null) child.kill();
      await Promise.race([exited, delay(3000)]);
    }
    cdp?.close();
    await rm(profile, { recursive: true, force: true, maxRetries: 8, retryDelay: 250 }).catch((error) => {
      lines.push(`ERROR cleaning temporary browser profile: ${error.code}`);
      process.exitCode = 2;
    });
    const log = join(evidence, `mobile-check-${stamp}.log`);
    await writeFile(log, `${lines.join("\n")}\n`);
    await writeFile(join(output, "report.json"), JSON.stringify(cases, null, 2));
    console.log(`${lines.at(-1)}\nEvidence: ${log}\nScreenshots: ${output}`);
  }
}

if (process.argv[2] === "--browser-path") {
  const path = browserPath();
  if (path) console.log(path);
  else process.exitCode = 1;
} else {
  await run();
}
