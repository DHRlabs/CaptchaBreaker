// Example: Puppeteer (Node) agent hitting CaptchaBreaker over HTTP.
// When you detect a CAPTCHA on a page, screenshot the CAPTCHA element,
// base64 it, and POST it to CaptchaBreaker. Then type the returned answer
// into the page.
//
//   node examples/agent_example.js

const puppeteer = require("puppeteer");

async function breakCaptcha(elementHandle, page) {
  // 1. Screenshot only the CAPTCHA element.
  const shot = await elementHandle.screenshot({ encoding: "base64" });

  // 2. Ask CaptchaBreaker. No API key needed for image CAPTCHAs.
  const resp = await fetch("http://127.0.0.1:8977/solve", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ type: "image", image: shot }),
  }).then((r) => r.json());

  if (!resp.success) {
    console.log("CaptchaBreaker failed:", resp.raw?.error);
    return null;
  }
  console.log("Solved:", resp.solution);


  // 3. Fill the answer into the visible CAPTCHA input.
  //    Adjust the selector to your site's captcha input.
  await page.type("#captcha-input, input[name*=captcha], .captcha input", resp.solution);
  return resp.solution;
}

async function main() {
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  await page.goto("https://example.com/form");

  const captchaEl = await page.$(".captcha img");
  if (captchaEl) {
    const answer = await breakCaptcha(captchaEl, page);
    console.log("Final captcha value:", answer);
  }
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
