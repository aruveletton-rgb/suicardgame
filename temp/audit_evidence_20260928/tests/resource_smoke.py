import asyncio, json, os, socket, subprocess, time, statistics
from pathlib import Path
import httpx
import websockets

ROOT=Path('/workspace/scratch/ddf75736e5b3/audit_latest/suicardgame')
OUT=Path('/workspace/scratch/ddf75736e5b3/audit_evidence')
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
env=dict(os.environ,SUICARDGAME_DATA_DIR=str(OUT/'resource_rooms'))
env.pop('TEST_MODE',None)
log=(OUT/'resource-server.log').open('w')
proc=subprocess.Popen(['/workspace/scratch/ddf75736e5b3/audit_venv/bin/python','-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=log)
ticks=os.sysconf('SC_CLK_TCK')
def sample():
    stat=Path(f'/proc/{proc.pid}/stat').read_text().split()
    status=Path(f'/proc/{proc.pid}/status').read_text().splitlines()
    vals={x.split(':')[0]:x.split(':')[1].strip() for x in status if ':' in x}
    return (int(stat[13])+int(stat[14]))/ticks,int(vals['VmRSS'].split()[0]),int(vals['VmHWM'].split()[0])

async def run():
    base=f'http://127.0.0.1:{port}/api/v1'
    async with httpx.AsyncClient(trust_env=False,timeout=5) as client:
        for _ in range(50):
            try:
                if (await client.get(base+'/health')).status_code==200:break
            except httpx.HTTPError:pass
            await asyncio.sleep(.1)
        sessions=[(await client.post(base+'/rooms',json={'nickname':'AuditHost'})).json()]
        code=sessions[0]['room_code']
        for n in range(4):sessions.append((await client.post(f'{base}/rooms/{code}/join',json={'nickname':f'Audit{n+1}'})).json())
        sixth=await client.post(f'{base}/rooms/{code}/join',json={'nickname':'AuditSixth'})
        sockets=[]; latencies=[]; events=[0]; snapshots={}; readers=[]
        async def reader(ws,player):
            async for raw in ws:
                event=json.loads(raw);events[0]+=1
                if event.get('event')=='private_snapshot':snapshots[player]=event
        for session in sessions:
            ws=await websockets.connect(f'ws://127.0.0.1:{port}/api/v1/rooms/{code}/ws')
            await ws.send(json.dumps({'event':'authenticate','player_id':session['player_id'],'session_id':session['session_id']}))
            sockets.append(ws);readers.append(asyncio.create_task(reader(ws,session['player_id'])))
        command_n=0
        async def cmd(s,kind,payload=None):
            nonlocal command_n
            command_n+=1;t=time.perf_counter()
            result=await client.post(f'{base}/rooms/{code}/commands',headers={'Authorization':'Bearer '+s['session_id']},json={'action_id':f'audit-{command_n}','player_id':s['player_id'],'command_type':kind,'payload':payload or {}})
            latencies.append((time.perf_counter()-t)*1000)
            return result
        cpu0,rss0,peak0=sample();start=time.perf_counter()
        ready=[(await cmd(s,'READY',{'ready':True})).status_code for s in sessions]
        started=await cmd(sessions[0],'START_GAME',{'seed':904})
        await asyncio.sleep(.1)
        draw=await cmd(sessions[0],'DRAW_CARD')
        for _ in range(10):
            for ws in sockets:await ws.send(json.dumps({'event':'ping'}))
            await asyncio.sleep(.2)
        await asyncio.sleep(2)
        wall=time.perf_counter()-start;cpu1,rss1,peak1=sample()
        result={'environment':'isolated local execution workspace, not target 2vCPU/2GiB server','workers':1,'rooms':1,'websocket_clients':5,'test_mode':False,'window_seconds':round(wall,3),'ready_status':ready,'start_status':started.status_code,'draw_status':draw.status_code,'sixth_join_status':sixth.status_code,'ws_received_events':events[0],'cpu_seconds':round(cpu1-cpu0,4),'cpu_percent_one_core':round((cpu1-cpu0)/wall*100,3),'rss_mib':round(rss1/1024,3),'peak_rss_mib':round(peak1/1024,3),'http_command_count':len(latencies),'http_command_ms_median':round(statistics.median(latencies),3),'http_command_ms_max':round(max(latencies),3),'limitations':'Short smoke: ready/start/one draw, 50 pings, brief idle. Not sustained game/complex effects, not concurrency capacity or target-server benchmark.'}
        (OUT/'resource-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        for ws in sockets:await ws.close()
        await asyncio.gather(*readers,return_exceptions=True)
try:asyncio.run(run())
finally:
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    log.close()
