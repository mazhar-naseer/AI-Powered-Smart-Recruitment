import{test,expect}from'@playwright/test';
test('landing page exposes both user journeys',async({page})=>{await page.goto('/');await expect(page.getByRole('heading',{name:/Smart Hiring/})).toBeVisible();await expect(page.getByRole('link',{name:"I’m an Employer"})).toBeVisible();await expect(page.getByText('Why SmartHire?')).toBeVisible()});
test('login validates required fields and registration switches roles',async({page})=>{await page.goto('/login');await expect(page.getByRole('heading',{name:'Login'})).toBeVisible();await page.goto('/register');await page.getByRole('button',{name:'Employer'}).click();await expect(page.getByLabel('Company name')).toBeVisible()});

