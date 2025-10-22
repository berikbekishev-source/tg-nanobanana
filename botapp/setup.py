   def setup_telegram():
       from .telegram import dp
       from .handlers import router as basic_router
       dp.include_router(basic_router)