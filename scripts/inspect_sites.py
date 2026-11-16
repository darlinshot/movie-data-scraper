import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_dtp(page):
    await page.goto('https://doanhthuphim.vn/tong-hop', wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(2000)
    info = {}
    info['url'] = page.url
    info['title'] = await page.title()
    info['show_more_texts'] = await page.evaluate(r"""
        () => Array.from(document.querySelectorAll('button,a,div[role=button]'))
          .map(e => (e.innerText||'').trim())
          .filter(t => t && /xem|thêm|more|load|tải/i.test(t))
          .slice(0,30)
    """)
    info['table_rows'] = await page.locator('table tbody tr').count()
    info['sample_rows'] = await page.evaluate(r"""
        () => Array.from(document.querySelectorAll('table tbody tr')).slice(0,5).map(tr => ({
          cells: Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()),
          hrefs: Array.from(tr.querySelectorAll('a[href]')).map(a => a.href),
        }))
    """)
    info['links'] = await page.evaluate(r"""
        () => Array.from(document.querySelectorAll('a[href]')).slice(0,40).map(a => ({text: (a.innerText||'').trim().slice(0,80), href: a.href}))
    """)
    return info

async def inspect_bov(page):
    await page.goto('https://v1.boxofficevietnam.com/', wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(2000)
    info = {}
    info['url'] = page.url
    info['title'] = await page.title()
    info['inputs'] = await page.evaluate(r"""
        () => Array.from(document.querySelectorAll('input')).map(i => ({type:i.type, placeholder:i.placeholder, name:i.name, id:i.id}))
    """)
    info['sample_links'] = await page.evaluate(r"""
        () => Array.from(document.querySelectorAll('a[href]')).slice(0,40).map(a => ({text:(a.innerText||'').trim().slice(0,80), href:a.href}))
    """)
    return info

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        result = {}
        result['doanhthuphim'] = await inspect_dtp(page)
        result['boxofficevietnam'] = await inspect_bov(page)
        await browser.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
