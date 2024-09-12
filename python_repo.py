import os
import re
import subprocess
from pathlib import Path

import chardet
import psutil
import toml
from func_timeout import func_set_timeout
from loguru import logger


def find_project_name(setup_filepath: str) -> str:
    with open(setup_filepath, "r", encoding="utf-8") as file:
        setup_content = file.read()
    setup_match = re.search(r'setuptools\.setup\s*\((.*?)\)', setup_content, re.DOTALL)
    if setup_match:
        setup_args = setup_match.group(1)
        name_match = re.search(r'\bname\s*=\s*[\'"]([^\'"]+)[\'"]', setup_args)
        if name_match:
            return name_match.group(1)
        else:
            logger.error("Project name not found inside setuptools.setup()")
    else:
        setup_match = re.search(r'setup\s*\((.*?)\)', setup_content, re.DOTALL)
        if setup_match:
            setup_args = setup_match.group(1)
            name_match = re.search(r'\bname\s*=\s*[\'"]([^\'"]+)[\'"]', setup_args)
            if name_match:
                return name_match.group(1)
            else:
                logger.error("Project name not found inside setup()")
        else:
            logger.error("Project name not found in `setup.py`")


class PythonRepo:
    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)
        self.venv_path = self.repo_path / ".venv"
        self.exec_path = self.venv_path / "bin" / "python"
        self.relate_exec_path = self.exec_path.relative_to(self.repo_path)
        self.env = []
        self.build_backend: str = None
        self.pypi_project_name: str = None
        self.env_var = os.environ.copy()
        self.env_var['PYDEVD_DISABLE_FILE_VALIDATION'] = '1'

    def load_environments_cfg(self):
        requirements_txt = self.repo_path / "requirements.txt"
        pyproject_toml = self.repo_path / "pyproject.toml"
        setup_py = self.repo_path / "setup.py"
        if requirements_txt.exists():
            with open(requirements_txt, 'rb') as f:  # for adapt unknown repo
                raw_data = f.read()
                result = chardet.detect(raw_data)
                encoding = result['encoding']

            with open(requirements_txt, "r", encoding=encoding) as file:
                self.env = [line.strip() for line in file.readlines() if (line.strip()) and (not line.startswith("#"))]

        if pyproject_toml.exists():
            with open(pyproject_toml, 'rb') as f:  # for adapt unknown repo
                raw_data = f.read()
                result = chardet.detect(raw_data)
                encoding = result['encoding']
            pyproject = toml.load(pyproject_toml)
            build_backend = pyproject.get('build-system', {}).get('build-backend', '')
            if 'poetry' in build_backend:
                self.build_backend = 'poetry'
            elif 'setuptools' in build_backend:
                self.build_backend = 'setuptools'
            else:
                logger.info(f"Unsupported build-backend: {build_backend}")

            # pypi project name
            self.pypi_project_name = pyproject.get('tool', {}).get('poetry', {}).get('name', None)
            if not self.pypi_project_name:
                self.pypi_project_name = pyproject.get('project', {}).get('name', None)

        if not self.pypi_project_name:
            if setup_py.exists():
                self.pypi_project_name = find_project_name(setup_py)
                self.build_backend = "setup.py"
            else:
                logger.warning(f"not a former python repo {self.repo_path}")

    def prepare_repo(self):
        with open(self.repo_path / "python_repo.toml", "r") as f:
            dd = toml.load(f)
        for k, cmd in dd["prepare"].items():
            logger.info(f"{self.repo_path} :: step {k}, executing cmd `{' '.join(cmd)}`")
            subprocess.run(cmd, cwd=str(self.repo_path), env=self.env_var)

    def config_repo(self):
        with open(self.repo_path / "python_repo.toml", "r") as f:
            dd = toml.load(f)
        for k, cmd in dd["resets"].items():
            logger.info(f"{self.repo_path} :: step {k}, executing cmd `{' '.join(cmd)}`")
            subprocess.run(cmd, cwd=str(self.repo_path), env=self.env_var)

    def generate_venv(self):
        if not self.venv_path.exists():
            subprocess.run(["python3", "-m", "venv", str(self.venv_path)], env=self.env_var)
        else:
            logger.info("Virtual environment already exists.")

    def config_venv(self):
        if not self.env:
            return
        subprocess.run([str(self.exec_path), "-m", "pip", "install", "--upgrade", "pip"], env=self.env_var)
        for package in self.env:
            subprocess.run([str(self.exec_path), "-m", "pip", "install", package], env=self.env_var)

    def install_pytest(self): subprocess.run([str(self.exec_path), "-m", "pip", "install", "pytest"], env=self.env_var)

    def build_and_install(self):
        try:
            if (self.build_backend is not None) and (self.pypi_project_name is not None):
                subprocess.run([str(self.exec_path), "-m", "pip", "uninstall", "-y", self.pypi_project_name], env=self.env_var)
                if self.build_backend == 'poetry':
                    subprocess.run(["poetry", "build"], env=self.env_var)
                elif self.build_backend == 'setuptools':
                    subprocess.run([str(self.exec_path), "-m", "pip", "install", "build"], env=self.env_var)
                    subprocess.run([str(self.relate_exec_path), "-m", "build"], cwd=str(self.repo_path), env=self.env_var)
                elif self.build_backend == "setup.py":
                    subprocess.run([str(self.exec_path), "-m", "pip", "install", "setuptools", "-U"], env=self.env_var)
                    subprocess.run([str(self.relate_exec_path), "setup.py", "bdist_wheel"],
                                   cwd=str(self.repo_path), env=self.env_var)
                else:
                    raise ValueError
                for file in os.listdir(self.repo_path / "dist"):
                    if file.endswith(".whl"):
                        subprocess.run([str(self.relate_exec_path), "-m", "pip", "install", f"dist/{file}"],
                                       cwd=str(self.repo_path), env=self.env_var)
        except Exception as e:
            logger.exception(e)

    def prepare_env(self):
        # self.prepare_repo()
        self.config_repo()
        # self.load_environments_cfg()
        # # self.generate_venv()
        # # self.config_venv()
        # # self.install_pytest()
        # self.build_and_install()

    @func_set_timeout(30)
    def run_test(self, test: str):
        logger.info(f"running {self.repo_path} | {test}")

        log_dir = os.path.join("log", self.repo_path.stem)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{test.split("::")[-1]}.log")

        with open(log_file, "w") as log_fh:

            process = subprocess.Popen([str(self.relate_exec_path), "-m", "pytest", test],
                                       cwd=str(self.repo_path),
                                       stdout=log_fh,
                                       stderr=log_fh,
                                       env=self.env_var)
            try:
                while True:
                    process_id = process.pid
                    process_memory = psutil.Process(process_id).memory_info().rss

                    # Check if memory usage exceeds 5GB (5 * 1024 * 1024 * 1024 bytes)
                    if process_memory > 5 * 1024 * 1024 * 1024:
                        process.terminate()
                        process.wait()
                        return False  # Out of Memory

                    return_code = process.poll()
                    if return_code is not None:
                        # If process finished and return code is not 0, it means test failed
                        if return_code != 0:
                            process.terminate()
                            process.wait()
                            return False  # Execution Error
                        else:
                            break  # Test passed, exit loop
            except Exception as e:
                process.terminate()
                process.wait()
                logger.exception(f"Error occurred: {e}")
                return False  # Other Error
            finally:
                process.terminate()
                process.wait()

        return True  # Test passed
