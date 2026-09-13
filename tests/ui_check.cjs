const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8011/login');
  await page.locator('#username').fill('demo');
  await page.locator('#password').fill('Demo-veneza-2026');
  await Promise.all([page.waitForURL('**/gerente-geral/dashboard'),page.getByRole('button',{name:'Entrar no sistema'}).click()]);
  await page.locator('.month-column').first().waitFor();
  const output = path.resolve('instance/previews');
  fs.mkdirSync(output,{recursive:true});
  await page.screenshot({path:path.join(output,'dashboard-desktop.png'),fullPage:true});
  await page.screenshot({path:path.join(output,'dashboard-overview.png')});
  for (const width of [1440,768,390,320]) {
    await page.setViewportSize({width,height:1000});
    await page.waitForTimeout(400);
    if (width === 390) await page.screenshot({path:path.join(output,'dashboard-mobile.png'),fullPage:true});
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) {
      console.log(await page.evaluate(() => [...document.querySelectorAll('body *')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>[el.tagName,el.className,el.getBoundingClientRect().right]).slice(0,20)));
      throw new Error(`Overflow dashboard ${width}`);
    }
  }
  await page.getByRole('button',{name:'Toggle navigation'}).click();
  await page.locator('#sidebarMenu.show').waitFor();
  await page.keyboard.press('Escape');
  await page.locator('#sidebarMenu.show').waitFor({state:'hidden'});
  await page.goto('http://127.0.0.1:8011/perfil');
  await page.screenshot({path:path.join(output,'profile-mobile.png'),fullPage:true});
  await page.getByLabel('Frequência',{exact:true}).selectOption('weekly');
  if (!(await page.locator('#weekday').isEnabled())) throw new Error('Weekly weekday disabled');
  for (const route of ['/gerente-geral/lojas','/gerente-geral/usuarios','/datas-curtas','/notifications','/gerente-geral/relatorio','/produtos/vencidos']) {
    await page.goto('http://127.0.0.1:8011'+route);
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`Overflow ${route}`);
  }
  await page.getByRole('button',{name:'Sair'}).click();
  await page.locator('#username').fill('setor');
  await page.locator('#password').fill('Demo-veneza-2026');
  await Promise.all([page.waitForURL('**/encarregado/produtos'),page.getByRole('button',{name:'Entrar no sistema'}).click()]);
  await page.goto('http://127.0.0.1:8011/datas-curtas');
  // Test camera-to-search integration with a simulated decoded result.
  await page.evaluate(() => {
    window.ZXing.BrowserMultiFormatReader = class {
      async decodeFromConstraints(constraints, video, callback) {
        if (constraints.video.facingMode.ideal !== 'environment') throw new Error('Rear camera not requested');
        callback({getText:()=> '7890000000000'});
      }
      reset() { window.cameraStopped = true; }
    };
  });
  await page.getByRole('button',{name:'Ler código com a câmera'}).click();
  await page.locator('#searchResultsContainer a').first().waitFor();
  if (await page.locator('#productSearchInput').inputValue() !== '7890000000000') throw new Error('Camera result missing');
  if (!(await page.evaluate(() => window.cameraStopped))) throw new Error('Camera not stopped');
  await page.locator('#productSearchInput').fill('Arroz');
  await page.getByRole('button',{name:'Pesquisar',exact:true}).click();
  await page.screenshot({path:path.join(output,'search-mobile.png'),fullPage:true});
  await page.locator('#searchResultsContainer a').first().click();
  await page.locator('#quantidade').fill('4');
  await page.locator('#validade').fill('2026-12-31');
  await page.getByRole('button',{name:'Registrar lote',exact:true}).click();
  if (!(await page.getByText('Lote registrado e notificações atualizadas.', {exact:false}).count())) throw new Error('Registration failed');
  await page.goto('http://127.0.0.1:8011/lotes/novo?manual=1');
  const manualName = `Pão artesanal de teste ${Date.now()}`;
  await page.locator('#nome_produto').fill(manualName);
  await page.locator('#quantidade').fill('20');
  await page.locator('#validade').fill('2026-12-31');
  await page.locator('#custo_unitario').fill('2.50');
  await page.getByRole('button',{name:'Registrar lote',exact:true}).click();
  await page.goto('http://127.0.0.1:8011/lotes?busca='+encodeURIComponent(manualName));
  await page.getByRole('link',{name:'Detalhes e baixas'}).first().click();
  await page.locator('#quantidade').fill('12');
  await page.locator('#valor_unitario').fill('4.00');
  await page.locator('#motivo').fill('Venda de teste');
  await page.getByRole('button',{name:'Confirmar baixa'}).click();
  await page.getByText('8 unidades restantes',{exact:true}).waitFor();
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Overflow lot detail');
  await page.screenshot({path:path.join(output,'lot-mobile.png'),fullPage:true});
  await page.goto('http://127.0.0.1:8011/historico');
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Overflow history');
  for (const route of ['/encarregado/produtos','/encarregado/vencidos','/encarregado/relatorio','/notifications']) {
    await page.goto('http://127.0.0.1:8011'+route);
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`Overflow ${route}`);
  }
  for (const [user,routes] of [['gerente',['/gerente/para-rebaixa','/gerente/em-rebaixa','/gerente/relatorio','/produtos/vencidos']],['auxiliar',['/auxiliar/dashboard']],['trocas',['/gerente-trocas/dashboard']]]) {
    await page.getByRole('button',{name:'Sair'}).click();
    await page.locator('#username').fill(user);
    await page.locator('#password').fill('Demo-veneza-2026');
    await page.getByRole('button',{name:'Entrar no sistema'}).click();
    await page.waitForURL(url=>!url.pathname.includes('/login'));
    for(const route of routes) {
      await page.goto('http://127.0.0.1:8011'+route);
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`Overflow ${route}`);
    }
  }
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('UI OK: dashboard 320/390/768/1440px, mobile pages for all roles, menu, weekly preferences, simulated camera, external selection and lot registration.');
  await browser.close();
})().catch(error => {console.error(error); process.exit(1);});
