from __future__ import annotations
import socket
import sys
import uvicorn
from app.config import settings

def port_free(host:str,port:int)->bool:
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(.3)
    try: return s.connect_ex((host,port))!=0
    finally: s.close()

if __name__=='__main__':
    if not port_free(settings.host,settings.port):
        print(f'Port {settings.port} is already in use.')
        print(f'Qanoni may already be running at http://{settings.host}:{settings.port}')
        print('If not, stop the process using that port or change PORT in .env.')
        sys.exit(2)
    uvicorn.run('app.main:app',host=settings.host,port=settings.port,reload=False,log_level='info')
