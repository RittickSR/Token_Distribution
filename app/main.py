from fastapi import FastAPI
from app.routers.token_router import router,lifespan


app = FastAPI(lifespan=lifespan)
app.include_router(router)


@app.get("/")
def root():
    return {"Service":"UP"}
