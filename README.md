# ReviewBot
Review Code with LLM

* Step 1: Install Dependencies

    ```
    pip install -r src/requirements.txt
    ```

* Step 2: Set Your API Key

    Create a `.reviewbot.env` in your **Home** directory:

    - Home (checked in this order): `~/.reviewbot.env`, `~/.env`, `~/.config/reviewbot/env`

    Put your key inside:

    ```
    OPENAI_API_KEY=sk-...
    ```

* Step 3: Run the Review

    Example: review your project code directory "myproj" for .cxx and .hxx files

    ```
    python src/ReviewBot myproj --extensions .cxx .hxx
    ```

    Or review all default extensions (.cxx .hxx .h .py)

    ```
    python src/ReviewBot myproj
    ```

* Optional:

    - Copy `src/models.example.yaml` to `models.yaml` and tweak models/temperatures.
