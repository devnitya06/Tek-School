@echo off
REM Check if virtual environment exists
IF NOT EXIST "env\" (
    echo Creating virtual environment...
    python -m venv env
)

REM Activate the virtual environment
call env\Scripts\activate

@REM REM Install required packages
@REM pip install --upgrade pip
@REM pip install -r requirements.txt

REM Run the FastAPI server
uvicorn app.main:app --reload
