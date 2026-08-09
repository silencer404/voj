import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index + 1 >= process.argv.length) {
    throw new Error(`missing option: ${name}`);
  }
  return process.argv[index + 1];
}

const sourceId = process.argv.at(-1);
const sourceNumber = /^P[0-9]{5}$/.test(sourceId) ? Number(sourceId.slice(1)) : NaN;
if (!Number.isInteger(sourceNumber) || sourceNumber < 0 || sourceNumber > 10000) {
  throw new Error("source id is outside the authorized range");
}

const playwrightPath = option("--playwright");
const browserPath = option("--browser");
const packageJson = JSON.parse(
  await readFile(resolve(playwrightPath, "package.json"), "utf8"),
);
const playwrightEntry =
  packageJson.module ?? packageJson.exports?.["."]?.import ?? packageJson.main;
const playwright = await import(
  pathToFileURL(resolve(playwrightPath, playwrightEntry)).href,
);
const browser = await playwright.firefox.launch({
  executablePath: browserPath,
  headless: true,
});

const sourceHosts = [
  "cn-hz.hydrooj.com",
  "ali-hk.hydro.ac",
  "xtom-jp.hydro.ac",
  "hk3.hydro.ac",
  "hydro.ac",
];

function retryableFetchError(error) {
  const message = String(error?.message ?? error);
  return error?.name === "TimeoutError" ||
    /(?:net::ERR_|NS_ERROR_|connection|timed?\s*out)/i.test(message);
}

try {
  let result;
  let lastError;
  for (const host of sourceHosts) {
    const page = await browser.newPage();
    try {
      await page.route("**/*", async route => {
        const restrictedPath = /\/(?:files?|attachments?)(?:\/|\?|$)|\.(?:zip|rar|7z|tar|gz)(?:\?|$)/i;
        if (restrictedPath.test(route.request().url())) {
          await route.abort();
        } else {
          await route.continue();
        }
      });
      const targetUrl = `https://${host}/d/hwod_oj/p/${sourceId}`;
      let response = await page.goto(
        targetUrl,
        { waitUntil: "domcontentloaded", timeout: 60000 },
      );
      if (await page.title() === "Cerberus Challenge") {
        await page.waitForFunction(
          () => document.title !== "Cerberus Challenge",
          null,
          { timeout: 180000 },
        );
        response = await page.goto(
          targetUrl,
          { waitUntil: "domcontentloaded", timeout: 60000 },
        );
      }
      await page.waitForFunction(
        expectedSourceId => [...document.scripts].some(script =>
          script.textContent?.includes("window.UiContextNew = ") &&
          script.textContent.includes(expectedSourceId)
        ),
        sourceId,
        { timeout: 60000 },
      );
      result = {
        status: response?.status() ?? 0,
        html: await page.content(),
      };
      break;
    } catch (error) {
      if (!retryableFetchError(error)) {
        throw error;
      }
      lastError = error;
    } finally {
      await page.close();
    }
  }
  if (!result) {
    throw lastError ?? new Error("all public source hosts failed");
  }
  process.stdout.write(JSON.stringify(result));
} finally {
  await browser.close();
}
