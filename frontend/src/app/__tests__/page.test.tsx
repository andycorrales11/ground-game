import { render } from '@testing-library/react';
import Home from '../page';
import { redirect } from 'next/navigation';

jest.mock('next/navigation', () => ({
  redirect: jest.fn(),
}));

describe('Home', () => {
  it('redirects to /draft', () => {
    render(<Home />);
    expect(redirect).toHaveBeenCalledWith('/draft');
  });
});
