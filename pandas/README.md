# Stash with Pandas

## 1. Environment file

.env file is a convenient place to store API keys and avoid having those in version controlled notebooks. Create .env file with your own API keys and other values:

```
cp env.sample .env
```

## 2. Install Python and related tools

### 2.1 Python and Pandas

Recommended: [Install Conda](https://conda.io/projects/conda/en/latest/user-guide/install/index.html) and create a new environment for it to keep Pandas separate from other Python environments.

```
conda create -c conda-forge -n name_of_my_env python pandas
conda activate name_of_my_env
```

Alternative: Install [Python](https://www.python.org/downloads/) and [Pandas](https://pandas.pydata.org/docs/getting_started/install.html).

### 2.2 pip packages

Install [stashapp-tools](https://github.com/stg-annon/stashapp-tools) and [dotenv](https://pypi.org/project/python-dotenv/):

```
pip install stashapp-tools python-dotenv
```

## 3. Install Visual Studio Code

Install [Visual Studio Code](https://code.visualstudio.com/) and following extensions:

- [Jupyter](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter)
- [Python Debugger](https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy)
- [Data Wrangler](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler)

## 4. Getting Started

After opening this repository in Visual Studio Code, remember to set correct kernel for Jupyter notebook: https://code.visualstudio.com/docs/datascience/jupyter-kernel-management

Now you can start experimenting with Stash and Pandas by looking at hello_world.ipynb.
