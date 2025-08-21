import uvicorn
from app.settings import settings


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)