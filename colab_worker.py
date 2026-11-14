"""Ancient Explained GPU render worker (Colab T4).

Pulls job zips from the `jobs` branch of the-ai-frontier-media, renders each on the GPU,
and pushes the finished MP4s to the `videos` branch (videos/<zip name><suffix>.mp4).
Progress goes to status.txt on the `jobs` branch (START / DONE / FAILED lines), logs to logs/<name>.log.

Colab cell (GPU runtime):
    import os; os.environ['GH_TOKEN'] = 'ghp_...'   # a token with push access to the-ai-frontier-media
    !git clone -q -b jobs https://$GH_TOKEN@github.com/trentrafferty2001-svg/the-ai-frontier-media /content/jobs
    !python /content/jobs/colab_worker.py
"""
import json, os, subprocess, sys, time, zipfile, shutil, re

TOKEN = os.environ['GH_TOKEN']
REPO = f'https://{TOKEN}@github.com/trentrafferty2001-svg/the-ai-frontier-media'
JOBS, VIDS, WORK, DEPS = '/content/jobs', '/content/videos', '/content/work', '/content/deps'
POLL = int(os.environ.get('POLL', '60'))


def sh(cmd, cwd=None, log=None, env=None):
    print('$', cmd, flush=True)
    p = subprocess.run(cmd, shell=True, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        with open(log, 'a') as f: f.write(f'$ {cmd}\n{p.stdout}\n')
    if p.returncode: raise RuntimeError(f'{cmd} -> {p.returncode}\n{p.stdout[-3000:]}')
    return p.stdout


def git_setup():
    for d in (JOBS, VIDS):
        if os.path.isdir(d):
            sh('git config user.name "colab-worker" && git config user.email "worker@colab"', cwd=d)
    if not os.path.isdir(VIDS):
        sh(f'git clone -q --depth 1 -b videos {REPO} {VIDS}')
        sh('git config user.name "colab-worker" && git config user.email "worker@colab"', cwd=VIDS)


def deps():
    if os.path.isdir(f'{DEPS}/node_modules/three') and os.path.isdir(f'{DEPS}/node_modules/playwright'): return
    os.makedirs(DEPS, exist_ok=True)
    sh('npm init -y >/dev/null && npm i -q three@0.169.0 playwright@1.49.1', cwd=DEPS)
    sh('npx playwright install --with-deps chromium', cwd=DEPS)
    sh('apt-get -qq install -y libvulkan1 mesa-vulkan-drivers vulkan-tools >/dev/null || true')


def status(line):
    sh('git pull -q --rebase', cwd=JOBS)
    with open(f'{JOBS}/status.txt', 'a') as f: f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + line + '\n')
    sh('git add -A; git commit -qm "worker: ' + line[:60].replace('"', "'") + '" && git push -q', cwd=JOBS)


def done_names():
    if not os.path.exists(f'{JOBS}/status.txt'): return set()
    out = set()
    for l in open(f'{JOBS}/status.txt'):
        m = re.search(r'(DONE|FAILED) (\S+)', l)
        if m: out.add(m.group(2))
    return out


def loudnorm_mux(video, mix, out, log):
    j = sh(f'ffmpeg -nostats -i "{mix}" -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | tail -14')
    m = json.loads(j[j.index('{'):j.rindex('}') + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    sh(f'ffmpeg -v error -y -i "{video}" -i "{mix}" -map 0:v -map 1:a -c:v copy -af "apad,{ln}" -ar 44100 -c:a aac -b:a 192k '
       f'-shortest -movflags +faststart "{out}"', log=log)


def run(name):
    log = f'{JOBS}/logs/{name}.log'; os.makedirs(f'{JOBS}/logs', exist_ok=True); open(log, 'w').close()
    W = f'{WORK}/{name}'; shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
    zipfile.ZipFile(f'{JOBS}/jobs/{name}.zip').extractall(W)
    job = json.load(open(f'{W}/job.json'))
    eng = f'{W}/engine'
    os.symlink(f'{DEPS}/node_modules', f'{eng}/node_modules')
    env = dict(os.environ, GL='vulkan', RES='1080', CRF='10', PRESET='fast', NODE_PATH=f'{DEPS}/node_modules')
    t0 = time.time()
    sh('node render.mjs video master.mp4 24', cwd=eng, log=log, env=env)
    sh('ffmpeg -v error -y -i master.mp4 -c:v libx264 -preset slow -crf 15 -profile:v high -pix_fmt yuv420p -movflags +faststart video.mp4', cwd=eng, log=log)
    outs = []
    for suffix, mix in job['mixes'].items():
        out = f'{VIDS}/videos/{name}{suffix}.mp4'; os.makedirs(os.path.dirname(out), exist_ok=True)
        loudnorm_mux(f'{eng}/video.mp4', f'{W}/{mix}', out, log); outs.append(out)
    sh('git pull -q --rebase && git add videos && git commit -qm "render ' + name + '" && git push -q', cwd=VIDS, log=log)
    return f'{int(time.time() - t0)}s ' + ' '.join(os.path.basename(o) for o in outs)


def main():
    git_setup(); deps()
    print(sh('vulkaninfo --summary 2>&1 | head -20 || true'))
    while True:
        sh('git pull -q --rebase', cwd=JOBS)
        todo = sorted(f[:-4] for f in os.listdir(f'{JOBS}/jobs') if f.endswith('.zip')) if os.path.isdir(f'{JOBS}/jobs') else []
        order = json.load(open(f'{JOBS}/order.json')) if os.path.exists(f'{JOBS}/order.json') else []
        todo.sort(key=lambda n: order.index(n) if n in order else 999)
        todo = [n for n in todo if n not in done_names()]
        if not todo:
            time.sleep(POLL); continue
        name = todo[0]
        status(f'START {name}')
        try:
            info = run(name); status(f'DONE {name} {info}')
        except Exception as e:
            print(e); status(f'FAILED {name} {str(e).splitlines()[0][:150]}')


if __name__ == '__main__':
    main()
