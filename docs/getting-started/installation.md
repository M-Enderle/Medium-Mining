# Installation Guide

This guide will walk you through the process of setting up the Medium-Mining project on your system.

## Prerequisites

Before installing Medium-Mining, ensure you have the following prerequisites:

- **Python**: Version 3.13 or newer is required
- **Poetry**: For dependency management
- **Git**: For cloning the repository (optional)

## Installing Python

If you don't have Python 3.13+ installed, you can download it from the [official Python website](https://www.python.org/downloads/).

To verify your Python version, run:

```bash
python --version
```

## Installing Poetry

Medium-Mining uses Poetry for dependency management. If you don't have Poetry installed, follow these steps:

=== "Linux/macOS"

    ```bash
    curl -sSL https://install.python-poetry.org | python3 -
    ```

=== "Windows PowerShell"

    ```powershell
    (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
    ```

Verify the installation:

```bash
poetry --version
```

## Installing Medium-Mining

There are two main ways to install Medium-Mining:

### Option 1: Clone from GitHub (Recommended)

1. Clone the repository:

```bash
git clone https://github.com/M-Enderle/Medium-Mining.git
cd Medium-Mining
```

2. Install dependencies using Poetry:

```bash
poetry install
```

3. Initialize Playwright browsers:

```bash
poetry run playwright install
```

### Option 2: Install from PyPI (not yet available)

!!! note
    This method will be available once the project is published to PyPI.

```bash
pip install medium-mining
```

## Initialize the Database

Before using Medium-Mining, you need to initialize the database:

```bash
poetry run python -m database.database
```

This will create a SQLite database in the project directory called `medium_articles.duckdb`.

## Verifying the Installation

To verify that Medium-Mining was installed correctly, you can run:

```bash
poetry run python -m scraper --help
```

You should see the help message with available commands and options.

## System-Specific Considerations

### Windows

On Windows, you might need to ensure that the Python Scripts directory is in your PATH.

### macOS

On macOS, you might need to install additional dependencies if you encounter issues with Playwright:

```bash
brew install webkit
```

### Linux

On Linux, you might need to install additional dependencies for Playwright:

```bash
# Ubuntu/Debian
apt-get update
apt-get install -y libwoff1 libopus0 libwebp6 libwebpdemux2 libenchant1c2a libgudev-1.0-0 libsecret-1-0 libhyphen0 libgdk-pixbuf2.0-0 libegl1 libnotify4 libxslt1.1 libevent-2.1-6 libgles2 libvpx5 libxcomposite1 libatk1.0-0 libatk-bridge2.0-0 libepoxy0 libgtk-3-0 libharfbuzz-icu0 libgstreamer-gl1.0-0 libgstreamer-plugins-bad1.0-0 libopenjp2-7 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 libjpeg-dev libpng-dev

# CentOS/RHEL
yum install -y pango.x86_64 libXcomposite.x86_64 libXcursor.x86_64 libXdamage.x86_64 libXext.x86_64 libXi.x86_64 libXtst.x86_64 cups-libs.x86_64 libXScrnSaver.x86_64 libXrandr.x86_64 GConf2.x86_64 alsa-lib.x86_64 atk.x86_64 gtk3.x86_64 ipa-gothic-fonts xorg-x11-fonts-100dpi xorg-x11-fonts-75dpi xorg-x11-utils xorg-x11-fonts-cyrillic xorg-x11-fonts-Type1 xorg-x11-fonts-misc
```

## Troubleshooting

If you encounter any issues during installation, refer to the [Common Issues](../faq/common-issues.md) section or open an issue on the [GitHub repository](https://github.com/M-Enderle/Medium-Mining/issues).

### Common Installation Issues

#### Poetry Environment Not Found

If Poetry can't find the environment, try:

```bash
poetry env use $(which python3.13)
```

#### Playwright Installation Fails

If Playwright installation fails, try installing it manually:

```bash
pip install playwright
playwright install
```

## Next Steps

Once you have successfully installed Medium-Mining, proceed to the [Quick Start](quick-start.md) guide to learn how to use the tool.