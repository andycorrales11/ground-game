// Adds toBeInTheDocument, toHaveAttribute and the rest of the DOM matchers.
// The package was already a dependency but was never loaded, so every assertion
// had to go through bare expect() on query results.
import '@testing-library/jest-dom';

// jsdom implements no layout, so it has no scrollIntoView. The board calls it
// to keep an arrow-key selection on screen.
window.Element.prototype.scrollIntoView = jest.fn();
