# XnneHangLab AI Coding Assistant: Context & Guidelines

`version: 2025.08.05-1`

## 1. Core Project Context

  - **Project:** XnneHangLab, a low-latency voice-based LLM interaction tool.
  - **Language:** Python >= 3.10
  - **Core Tech Stack:**
      - **Backend:** FastAPI, Pydantic v2, Uvicorn, fully async
      - **Real-time Communication:** WebSockets
      - **Package Management:** `uv` (version ~= 0.8, as of 2025 August) (always use `uv run`, `uv sync`, `uv add`, `uv remove` to do stuff instead of `pip`)
  - **Primary Goal:** Achieve end-to-end latency below 500ms (user speaks -> AI voice heard). Performance is critical.
  - **Key Principles:**
      - **Offline-Ready:** Core functionality MUST work without an internet connection.
      - **Separation of Concerns:** Strict frontend-backend separation.
      - **Clean code:** Clean, testable, maintainable code, follows best practices of python 3.10+ and does not write deprecated code.

Some key files and directories:

```
doc/                 # A deprecated directory
frontend/            # Compiled web frontend artifacts (from git submodule)
config/
    lab.toml         # Configuration for main program
    gsv_config.json  # model parameter settings for gpt-sovits, not important
    vtuber.yaml      # config file for live2d model setting
src/lab/ # Project source code
    config_manager/
        config.py    # Pydantic models for configuration validation
run_server.py        # Entrypoint to start the application
configs/
    lab.toml         # User's configuration file, generated from a template
tests/               # Test cases.
justfile             # useful scripts like start or install models. 
```

### 1.1. Repository Structure

- Frontend Repository: The frontend is a React application developed in a separate repository: `Open-LLM-VTuber-Web`. Its built artifacts are integrated into the `frontend/` directory of this backend repository via a git submodule.
- Scripts: All scripts which are used frequently are in `justfile` like `just start`, `just fmt`, `just lint`.
- Dependency Management: All based on uv.
 
### 1.2. Configuration Files

- Configuration templates are located in the `configs/` directory:
- `lab.toml`: Template for user.
- Configuration is validated on load using the Pydantic models defined in `src/lab/config_manager/config.py`. Any changes to configuration options must be reflected in these models.

## 2. Overarching Coding Philosophy

  - **Simplicity and Readability:** Write code that is simple, clear, and easy to understand. Avoid unnecessary complexity or premature optimization. Follow the Zen of Python.
  - **Single Responsibility:** Each function, class, and module should do one thing and do it well.
  - **Performance-Aware:** Be mindful of performance. Avoid blocking operations in async contexts. Use efficient data structures and algorithms where it matters.
  - **Adherence to Best Practices**: Write clean, testable, and robust code that follows modern Python 3.10+ idioms. Adhere to the best practices of our core libraries (FastAPI, Pydantic v2).

## 3. Detailed Coding Standards

### 3.1. Formatting & Linting (Ruff)

  - All Python code **MUST** be formatted with `uv run ruff format`.
  - All Python code **MUST** pass `uv run ruff check` without errors.
  - Import statements should be grouped by standard library, third-party, and local modules and sorted alphabetically (PEP 8).

### 3.2. Naming Conventions (PEP 8)

  - Use `snake_case` for all variables, functions, methods, and module names.
  - Use `PascalCase` for class names.
  - Choose descriptive names. Avoid single-letter names except for loop counters or well-known initialisms.

### 3.3. Type Hints (CRITICAL)

  - Target Python 3.10+. Use modern type hint syntax.
  - **DO:** Use `|` for unions (e.g., `str | None`).
  - **DON'T:** Use `Optional` from `typing` (e.g., `Optional[str]`).
  - **DO:** Use built-in generics (e.g., `list[int]`, `dict[str, float]`).
  - **DON'T:** Use capitalized types from `typing` (e.g., `List[int]`, `Dict[str, float]`).
  - All function and method signatures (arguments and return values) **MUST** have accurate type hints. If third party libraries made it impossible to fix type errors, suppress the type checker.

### 3.4. Docstrings & Comments (CRITICAL)

  - All public modules, functions, classes, and methods **MUST** have a docstring in English or Chinese.
  - Use the **Google Python Style** for docstrings.
  - Docstrings **MUST** include:
    1.  Summary.
    2.  `Args:` section describing each parameter, its type, and its purpose.
    3.  `Returns:` section describing the return value, its type, and its meaning.
    4.  (Optional but encouraged) `Raises:` section for any exceptions thrown.
  - All other code comments must also be in English or Chinese.

### 3.5. Logging

  - Use the `loguru` module for all informational or error output.
  - Log messages should be in English or Chinese, clear, and informative. Use emoji when appropriate.


### 3.6. For PR

  - run `just fmt` to format the code first.
  - Then run `just lint` to make sure code ruff lint check is passed.
  - After all you can open a PR. 

And if you write a can-be-re-used function. You should make sure you have test cases for it in `tests` and run `just test` to test it.

## 4. Architectural Principles

### 4.1. Dependency Management

  - First, try to solve the problem using the Python standard library or existing project dependencies defined in `pyproject.toml`.
  - If a new dependency is required, it must have a compatible license and be well-maintained.
  - Use `uv add`, `uv remove`, `uv run` instead of pip to manage dependencies.
  - Different dependencies are managed by group, it was separate into different group depends on what module it is in.
  - If different module depends on the same dependency, it should be moved to base-module like tts-base or base.
  - For all new packages, it should be considered to be manage by groups.

### 4.2. Cross-Platform Compatibility

  - All core logic **MUST** run on macOS, Windows, and Linux.
  - If a feature is platform-specific (e.g., uses a Windows-only API) or hardware-specific (e.g., CUDA), it **MUST** be an optional component. The application should start and run core features even if that component is not available. Use graceful fallbacks or clear error messages.