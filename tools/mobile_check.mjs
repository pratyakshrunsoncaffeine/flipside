import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { platform, release, tmpdir } from "node:os";
import { delimiter, join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const viewports = [[320, 640], [360, 780], [390, 844], [414, 896], [768, 1024], [844, 390]];
const root = fileURLToPath(new URL("../", import.meta.url));
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const evidence = resolve(process.env.MOBILE_EVIDENCE_DIR ?? join(root, "evidence"));
const output = resolve(process.env.MOBILE_ARTIFACTS ?? join(root, "mobile-check-screenshots", stamp));
const screenshots = process.env.MOBILE_SCREENSHOTS === "1";

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
    if (el.id) return `${el.localName}#${el.id}`;
    const classes = [...el.classList].filter((item) => !["on", "now", "done", "shown"].includes(item));
    const attribute = el.matches("a[href]") ? "href" : el.hasAttribute("aria-label") ? "aria-label" : null;
    const suffix = attribute ? `[${attribute}=${JSON.stringify(el.getAttribute(attribute))}]` : "";
    return el.localName + classes.map((item) => `.${item}`).join("") + suffix;
  }
  if (innerWidth !== width || scrollWidth > innerWidth) {
    const dimensions = `expected width ${width}px, innerWidth ${innerWidth}px, scrollWidth ${scrollWidth}px`;
    const overflowing = [...document.body.querySelectorAll("*")]
      .filter((el) => visible(el) && el.getBoundingClientRect().right > Math.min(innerWidth, width) + 1);
    if (overflowing.length) {
      for (const el of overflowing) report(el, "overflow", dimensions);
    } else {
      issues.push({ area: "page", kind: "overflow", selector: "html", message: dimensions });
    }
  }

  function visible(el) {
    if (el.closest("[hidden], [inert], [aria-hidden='true']")) return false;
    const css = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return css.visibility === "visible" && el.getClientRects().length > 0
      && css.clipPath === "none" && css.clip === "auto" && (rect.width > 1 || rect.height > 1);
  }
  function report(el, kind, message) {
    const label = el.getAttribute("aria-label") ?? el.textContent.trim();
    const section = el.closest("section[id], header[id]");
    const area = section?.id ?? (el.closest("footer") ? "footer" : el.closest("nav") ? "nav" : "page");
    const name = label ? `(${label.replace(/\s+/g, " ").slice(0, 72)}) ` : "";
    issues.push({ area, kind, selector: selector(el), message: `${name}${message}` });
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
    report(el, "tap", `${rect.width.toFixed(1)}x${rect.height.toFixed(1)}px (44x44 minimum)`);
  }

  const text = "main p, main li, section p, section li, header p, header li, "
    + "label, figcaption, caption, code, pre, input, select, textarea";
  for (const el of document.querySelectorAll(text)) {
    if (!visible(el)) continue;
    const isLabel = el.matches('li') && el.closest('[data-mobile="labels"]');
    const min = !isLabel && el.matches("p, li, input, select, textarea") ? 16 : 12;
    const size = parseFloat(getComputedStyle(el).fontSize);
    if (size < min) report(el, "text", `${size}px (${min} minimum)`);
  }
  return issues;
}

async function checkPage(cdp, origin, page, width, height) {
  let targetId;
  let sessionId;
  let step = "create window";
  try {
    ({ targetId } = await cdp.call("Target.createTarget", {
      url: "about:blank", newWindow: true, background: false,
    }));
    step = "configure emulation";
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
    await call("Emulation.setFocusEmulationEnabled", { enabled: true });
    step = "load";
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
    // Chromium can suspend animation frames for a background target.
    const frame = `new Promise(resolve => {
      const timeout = setTimeout(resolve, 100);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        clearTimeout(timeout);
        resolve();
      }));
    })`;
    const settled = `(async () => {
      const deadline = performance.now() + 1000;
      do {
        await ${frame};
      } while (performance.now() < deadline && document.getAnimations().some(a => a.playState === "running"));
    })()`;
    step = "fonts";
    await evaluate(`Promise.race([document.fonts.ready, new Promise(resolve => setTimeout(resolve, 1500))]).then(() => ${frame})`);
    step = "scroll";
    const { scrollHeight, innerHeight } = await evaluate(
      "({ scrollHeight: document.documentElement.scrollHeight, innerHeight })",
    );
    for (let y = 0; y < scrollHeight; y += innerHeight) {
      await evaluate(`scrollTo({ top: ${y}, behavior: "instant" }); ${frame}`);
    }
    await evaluate(`scrollTo({ top: 0, behavior: "instant" }); ${frame}`);
    step = "settle";
    await evaluate(settled);
    step = "inspect";
    const issues = await evaluate(`(${inspectPage})(${width})`);
    if (screenshots) {
      const sections = await evaluate("Array.from(document.querySelectorAll('header[id], section[id], footer[id]'), el => el.id)");
      for (const id of ["viewport", ...sections]) {
        step = `screenshot ${id}`;
        await evaluate(`(async () => {
          const el = document.getElementById(${JSON.stringify(id)});
          if (el) el.scrollIntoView({ behavior: "instant" });
          else scrollTo({ top: 0, behavior: "instant" });
          await ${frame};
        })()`);
        await evaluate(settled);
        const { data } = await call("Page.captureScreenshot", { format: "png", optimizeForSpeed: true });
        await writeFile(join(output, `${page.slice(0, -5)}-${width}x${height}-${id}.png`), Buffer.from(data, "base64"));
      }
    }
    return [...issues, ...[...errors].map((message) => ({
      area: "page", kind: "console", selector: "document", message,
    }))];
  } catch (error) {
    throw new Error(`${page} ${width}x${height} (${step}): ${error.message}`, { cause: error });
  } finally {
    if (sessionId) cdp.listen(sessionId);
    if (targetId) await cdp.call("Target.closeTarget", { targetId });
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
    server = spawn(process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3"), [
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
    let browserStderr = "";
    child = spawn(executable, [
      "--headless=new", "--no-first-run", "--disable-background-networking", "--disable-dev-shm-usage",
      "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--enable-unsafe-swiftshader",
      "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
      `--user-data-dir=${profile}`, "about:blank",
    ], { stdio: ["ignore", "ignore", "pipe"], windowsHide: true });
    child.on("error", (error) => { launchError = error; });
    child.stderr.setEncoding("utf8").on("data", (text) => {
      browserStderr = (browserStderr + text).split(/\r?\n/).slice(-31).join("\n");
    });
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
    }, "browser startup", 30000).catch((error) => {
      throw new Error(`${error.message}\n${browserStderr.trim()}`.trim());
    });
    cdp = await connect(`ws://127.0.0.1:${port}${path}`);
    const { product } = await cdp.call("Browser.getVersion");
    lines.push(`${product} | ${platform()} ${release()} | touch emulation | DPR 2 | CSS pixels | offline font fallback`);
    const matrix = ["index.html", "verify.html"].flatMap((page) =>
      viewports.map(([width, height]) => ({ page, width, height }))
    );
    for (let start = 0; start < matrix.length; start += 4) {
      const group = await Promise.allSettled(matrix.slice(start, start + 4).map(async (entry) => ({
        ...entry,
        issues: await checkPage(cdp, `http://127.0.0.1:${httpPort}`, entry.page, entry.width, entry.height),
      })));
      for (const result of group) {
        if (result.status === "rejected") throw result.reason;
        const { page, width, height, issues } = result.value;
        cases.push(result.value);
        const label = `${issues.length ? "FAIL" : "PASS"} ${page} ${width}x${height} (${issues.length} issues)`;
        lines.push(label, ...issues.map(({ area, kind, selector, message }) => (
          `  [${area}/${kind}] ${selector}: ${message}`
        )));
        console.log(label);
      }
    }
    const passed = cases.filter((entry) => !entry.issues.length).length;
    lines.push(`RESULT ${passed === matrix.length ? "PASS" : "FAIL"} ${passed}/${matrix.length} page-viewports`);
    process.exitCode = passed === matrix.length ? 0 : 1;
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
    console.log(`${lines.at(-1)}\nEvidence: ${log}\nArtifacts: ${output}`);
  }
}

if (process.argv[2] === "--browser-path") {
  const path = browserPath();
  if (path) console.log(path);
  else process.exitCode = 1;
} else {
  await run();
}
