from setuptools import setup, find_packages


with open("README.md", encoding="UTF-8") as file:
    readme = file.read()

with open("requirements.txt", "r", encoding="utf-8") as file:
    requirements = [line.strip() for line in file]

setup(
    name="vocabmaster",
    version="0.1.2",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "vocabmaster = vocabmaster.cli:vocabmaster",
        ]
    },
    long_description=readme,
    long_description_content_type="text/markdown",
    author="sderev",
)
