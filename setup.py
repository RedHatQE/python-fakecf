#!/usr/bin/env python

from setuptools import setup
import glob

setup(name='fakecf',
    version='0.1',
    description='Python library to emulate CloudForamtion stuff when it is not accessible',
    author='Vitaly Kuznetsov',
    author_email='vitty@redhat.com',
    url='https://github.com/RedHatQE/python-fakecf',
    license="GPLv3+",
    packages=[
        'fakecf'
        ],
    classifiers=[
            'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
            'Programming Language :: Python',
            'Topic :: Software Development :: Libraries :: Python Modules',
            'Operating System :: POSIX',
            'Intended Audience :: Developers',
            'Development Status :: 4 - Beta'
    ]
)
