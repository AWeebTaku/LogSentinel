import uvicorn

if __name__ == "__main__":
    # localhost only: the API has no authentication
    uvicorn.run("logsentinel.api.app:app", host="127.0.0.1", port=8000)
