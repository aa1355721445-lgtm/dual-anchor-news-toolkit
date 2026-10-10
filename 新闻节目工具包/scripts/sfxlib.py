"""Procedural sound effects (no samples needed)."""
import numpy as np

def make_sfx(SR=48000, seed=3):
    rng=np.random.default_rng(seed)
    def t_(d): return np.arange(int(d*SR))/SR
    def env(d,a=.005,dec=8):
        t=t_(d); e=np.exp(-t*dec); n=int(a*SR); e[:n]*=np.linspace(0,1,n); return e
    def lp(x,k):  # simple one-pole lowpass k in (0,1)
        y=np.zeros_like(x); s=0.
        for i in range(len(x)): s+=k*(x[i]-s); y[i]=s
        return y
    def bp_noise(d,f0,f1,q=.5):
        n=int(d*SR); x=rng.standard_normal(n); X=np.fft.rfft(x); f=np.fft.rfftfreq(n,1/SR)
        fc=np.sqrt(f0*f1); bw=abs(f1-f0)+fc*q; X*=np.exp(-((f-fc)/bw)**2); return np.fft.irfft(X,n)
    def sweep(d,f0,f1,curve=1.):
        t=t_(d); f=f0+(f1-f0)*(t/d)**curve; return np.sin(2*np.pi*np.cumsum(f)/SR)
    def norm(x,v): return x/ (np.abs(x).max()+1e-9)*v
    S={}
    S['pop']=norm(sweep(.07,950,320,.6)*env(.07,.002,45)+.15*rng.standard_normal(int(.07*SR))*env(.07,.001,120),.22)
    t=t_(.28); f=320+520*(t/.28)**.5+40*np.sin(2*np.pi*17*t); boing=np.sin(2*np.pi*np.cumsum(f)/SR)
    S['boing']=norm((boing+.25*np.sign(boing))*env(.28,.004,9),.2)
    def whoosh(d,up=True):
        n=int(d*SR); x=rng.standard_normal(n); out=np.zeros(n); seg=1024
        for i in range(0,n,seg):
            k=i/n; fc=(400+2600*k) if up else (3000-2400*k); X=np.fft.rfft(x[i:i+seg]); f=np.fft.rfftfreq(len(x[i:i+seg]),1/SR)
            X*=np.exp(-((f-fc)/(fc*.7))**2); out[i:i+seg]=np.fft.irfft(X,len(x[i:i+seg]))
        tt=t_(d); e=np.sin(np.pi*np.clip(tt/d,0,1))**1.6
        return norm(lp(out*e,.6),1.)
    S['whoosh']=whoosh(.5)*.3
    S['whoosh_out']=whoosh(.5,False)*.28
    S['swoosh']=whoosh(.42)*.34
    tt=t_(.2); m=np.sin(2*np.pi*70*tt)*(8*np.exp(-tt*18)); zap=np.sin(2*np.pi*1500*tt+m)*env(.2,.002,16); zap=np.round(zap*6)/6
    S['zap']=norm(zap+.3*bp_noise(.2,3000,6000)*env(.2,.001,30),.16)
    th=sweep(.32,140,42,.4)*env(.32,.002,11)+.5*lp(rng.standard_normal(int(.32*SR)),.08)*env(.32,.001,25)
    S['thump']=norm(th,.55)
    def ping(f,d=.5,dec=9): tt=t_(d); return np.sin(2*np.pi*f*tt)*env(d,.002,dec)
    tw=np.zeros(int(.5*SR))
    for i,fq in enumerate([2350,3130,2790,3720]): o=int(i*.045*SR); p=ping(fq,.5-i*.045,11); tw[o:o+len(p)]+=p
    S['twinkle']=norm(tw,.11)
    ding=sum(a*ping(f,1.0,dec) for f,a,dec in [(1318,1,4),(2637,.5,6),(3951,.25,8),(5274,.12,10)])
    S['ding']=norm(ding,.17)
    S['hit']=norm(.8*th[:int(.32*SR)]+np.pad(ding[:int(.32*SR)],(0,0))*.6,.5)
    for k,v in S.items(): S[k]=v.astype(np.float32)
    
    return S
