import React from 'react';

const Header: React.FC = () => {
    return (
        <header className="bg-yellow-400 border-4 border-black p-4 text-center">
            <h1 className="text-4xl font-extrabold uppercase tracking-widest text-black">
                Ground Game
            </h1>
            <nav className="mt-4">
                <ul className="flex justify-center space-x-4">
                    <li>
                        <a
                            href="/"
                            className="px-3 py-1 border-2 border-black bg-white text-black hover:bg-black hover:text-white transition duration-150"
                        >
                            Home
                        </a>
                    </li>
                    <li>
                        <a
                            href="/draft"
                            className="px-3 py-1 border-2 border-black bg-white text-black hover:bg-black hover:text-white transition duration-150"
                        >
                            Draft
                        </a>
                    </li>
                    <li>
                        <a
                            href="#"
                            className="px-3 py-1 border-2 border-black bg-white text-black hover:bg-black hover:text-white transition duration-150"
                        >
                            League
                        </a>
                    </li>
                </ul>
            </nav>
        </header>
    );
};

export default Header;