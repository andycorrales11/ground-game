
import nextJest from 'next/jest.js'
 
const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files in your test environment
  dir: './',
})
 
// Add any custom config to be passed to Jest
const config = {
  coverageProvider: 'v8',
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  /*
    The tsconfig `@/*` alias, spelled out for Jest's resolver.

    Static imports already worked without this, because the SWC transform
    rewrites their specifiers using tsconfig's paths. `jest.mock('@/lib/api')`
    is a plain string argument and never gets rewritten, so it failed to
    resolve -- which is exactly the form the page tests need.
  */
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
}
 
// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
export default createJestConfig(config)
