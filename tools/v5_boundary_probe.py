import json,os,socket
result={}
try:s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.close();result['network_denied']=False
except OSError:result['network_denied']=True
try:
 with open('/srv/samo-v5-acceptance/code/write-probe','w') as f:f.write('not allowed')
 result['source_write_denied']=False
except OSError:result['source_write_denied']=True
parent=open('/proc/self/cgroup').read();r,w=os.pipe();pid=os.fork()
if pid==0:
 os.close(r);os.write(w,str(open('/proc/self/cgroup').read()==parent).encode());os.close(w);os._exit(0)
os.close(w);result['child_same_cgroup']=os.read(r,100).decode()=='True';os.close(r);os.waitpid(pid,0)
print(json.dumps(result));assert all(result.values())
