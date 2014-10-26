import os

from setuptools import setup, find_packages


version = '1.0.0'

here = os.path.abspath(os.path.dirname(__file__))

README = open(os.path.join(here, 'README.rst')).read()

setup(name='nicovideo',
      version=version,
      description="A library for Nicovideo",
      long_description=README,
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Topic :: Software Development :: Libraries'
          ],
      keywords='nicovideo',
      author='Naoya Inada',
      author_email='naoina@kuune.org',
      url='https://github.com/naoina/nicovideo',
      license='MIT',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      )
