/* eslint-disable @typescript-eslint/no-require-imports */
const { chromium } = require('playwright');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForCondition(check, timeoutMs, intervalMs = 250) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const ready = await check();
    if (ready) {
      return true;
    }
    await sleep(intervalMs);
  }
  return false;
}

(async () => {
  const results = {
    authCall: false,
    chatWs: false,
    monitorWs: false,
    adminUsers: false,
    adminPolicies: false,
    adminSources: false,
    adminAudit: false,
    pipelineEvent: false,
    chatTokenFrame: false,
    chatTerminalFrame: false,
    chatRenderedInUi: false,
  };

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1540, height: 980 } });

  page.on('response', (response) => {
    const url = response.url();
    const statusOk = response.status() < 400;

    if (url.includes('/auth/google')) {
      results.authCall = results.authCall || statusOk;
    }
    if (url.includes('/admin/users')) {
      results.adminUsers = results.adminUsers || statusOk;
    }
    if (url.includes('/admin/role-policies')) {
      results.adminPolicies = results.adminPolicies || statusOk;
    }
    if (url.includes('/admin/data-sources')) {
      results.adminSources = results.adminSources || statusOk;
    }
    if (url.includes('/admin/audit-log')) {
      results.adminAudit = results.adminAudit || statusOk;
    }
  });

  page.on('websocket', (ws) => {
    const wsUrl = ws.url();
    if (wsUrl.includes('/chat/stream')) {
      results.chatWs = true;
    }
    if (wsUrl.includes('/admin/pipeline/monitor')) {
      results.monitorWs = true;
    }

    ws.on('framereceived', (event) => {
      const payload = event.payload;
      if (typeof payload !== 'string') {
        return;
      }

      let frame = null;
      try {
        frame = JSON.parse(payload);
      } catch {
        frame = null;
      }

      if (frame && typeof frame === 'object') {
        const frameRecord = frame;
        if (frameRecord.type === 'token') {
          results.chatTokenFrame = true;
        }
        if (frameRecord.type === 'done' || frameRecord.type === 'error') {
          results.chatTerminalFrame = true;
        }
      }

      if (
        payload.includes('pipeline_start') ||
        payload.includes('stage_event') ||
        payload.includes('pipeline_complete')
      ) {
        results.pipelineEvent = true;
      }
    });
  });

  try {
    await page.goto('http://localhost:8080/chat', {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });

    await page.evaluate(() => window.localStorage.clear());
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });

    await page.getByRole('button', { name: /ithead@ipeds\.local/i }).click();
    await page.waitForSelector('text=/::\\s*it_head/i', { timeout: 30000 });

    await sleep(2500);

    await page.getByRole('link', { name: /Admin Console/i }).click();
    await page.waitForURL('**/admin', { timeout: 30000 });

    await page.getByRole('button', { name: /Refresh Admin/i }).click();

    await page.getByRole('link', { name: /Chat Workspace/i }).click();
    await page.waitForURL('**/chat', { timeout: 30000 });

    const chatInput = page.getByPlaceholder('Ask a campus question...');
    await chatInput.fill('Give me a quick cross-domain campus risk and enrollment summary.');
    await page.getByRole('button', { name: /^Send$/ }).click();

    await waitForCondition(() => results.chatTokenFrame || results.chatTerminalFrame, 45000, 300);

    const chatSeenInUi = await waitForCondition(async () => {
      const bodyText = await page.locator('body').innerText();
      return (
        bodyText.includes('source:') ||
        bodyText.includes('Streaming failed.') ||
        bodyText.includes('cannot access business data chat')
      );
    }, 45000, 500);
    results.chatRenderedInUi = chatSeenInUi;

    await page.getByRole('link', { name: /Pipeline Monitor/i }).click();
    await page.waitForURL('**/monitor', { timeout: 30000 });

    const pipelineSeenInUi = await waitForCondition(async () => {
      const bodyText = await page.locator('body').innerText();
      return bodyText.includes('Pipeline started:') || bodyText.includes('Stage ');
    }, 30000, 500);
    if (pipelineSeenInUi) {
      results.pipelineEvent = true;
    }

    await waitForCondition(
      () =>
        results.adminUsers &&
        results.adminPolicies &&
        results.adminSources &&
        results.adminAudit,
      30000,
      250
    );

    await page.screenshot({ path: '/tmp/zta-smoke.png', fullPage: true });

    const requiredChecks = [
      'authCall',
      'chatWs',
      'monitorWs',
      'adminUsers',
      'adminPolicies',
      'adminSources',
      'adminAudit',
      'pipelineEvent',
      'chatTerminalFrame',
      'chatRenderedInUi',
    ];

    const failedChecks = requiredChecks.filter((name) => !results[name]);

    console.log('SMOKE_RESULTS', JSON.stringify(results, null, 2));
    console.log('SMOKE_SCREENSHOT', '/tmp/zta-smoke.png');

    if (failedChecks.length > 0) {
      throw new Error(`Smoke checks failed: ${failedChecks.join(', ')}`);
    }

    console.log('SMOKE_STATUS PASS');
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error('SMOKE_STATUS FAIL');
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
