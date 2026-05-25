
  # UNITED EXPLORATION_07022026

  This is a code bundle for UNITED EXPLORATION_07022026. The original project is available at https://www.figma.com/design/jOCLVmkKN6hOKxzJ7F4iYZ/UNITED-EXPLORATION_07022026.

  ## Running the code

  Run `npm i` to install the dependencies.

  Run `npm run dev` to start the development server.

  ## UI testing (Playwright)

  - Install deps: `npm i`
  - Install browsers (first time only): `npx playwright install --with-deps`
  - Start the app (and backend API) as usual
  - Run the timer sync test:
    - `E2E_EMAIL=employee@gmail.com E2E_PASSWORD=test@12345 npm run test:e2e`

  Optional:
  - Override the base URL: `E2E_BASE_URL=http://localhost:5173 npm run test:e2e`
  