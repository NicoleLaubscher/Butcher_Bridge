# ButcherBridge Decision Support

This is the complete GitHub-ready source for the ButcherBridge website. The interface, styling, sample data, calculations, validations and interactions are the same as the current hosted version.

## Run it on your computer

You only need Node.js 18 or newer. No packages need to be installed.

```bash
npm start
```

Then open [http://localhost:4173](http://localhost:4173) in your browser.

Run the calculation tests with:

```bash
npm test
```

## Put it on GitHub

1. Create a new empty GitHub repository, for example `butcherbridge-decision-support`.
2. Extract this project and open a terminal inside the project folder.
3. Run the following commands, replacing `YOUR-USERNAME` with your GitHub username:

```bash
git init
git add .
git commit -m "Add ButcherBridge decision-support website"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/butcherbridge-decision-support.git
git push -u origin main
```

4. In the GitHub repository, open **Settings → Pages**.
5. Under **Build and deployment**, set **Source** to **GitHub Actions**.
6. Open the **Actions** tab and wait for “Deploy ButcherBridge to GitHub Pages” to finish.

Your website will normally be available at:

```text
https://YOUR-USERNAME.github.io/butcherbridge-decision-support/
```

Every future push to the `main` branch automatically republishes the website.

## Important data note

Scenario changes are stored in the current browser using `localStorage`. They are not uploaded to a database and will not automatically appear in a different browser or on another device.

## Main files

- `index.html` — website structure and content
- `styles.css` — the full visual design and responsive layout
- `app.js` — interface interactions and rendering
- `engine.mjs` — feasibility, price-tier and landed-cost calculations
- `tests/engine.test.mjs` — calculation tests
- `.github/workflows/deploy-pages.yml` — automatic GitHub Pages deployment
