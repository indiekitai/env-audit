from setuptools import setup

setup(
    name='env-audit',
    version='0.1.0',
    description='Scan a codebase for environment variables and generate documented .env.example',
    author='IndieKit',
    author_email='hello@indiekit.ai',
    url='https://github.com/indiekitai/env-audit',
    py_modules=['env_audit'],
    entry_points={
        'console_scripts': [
            'env-audit=env_audit:main',
        ],
    },
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Documentation',
        'Topic :: Utilities',
    ],
)
