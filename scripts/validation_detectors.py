"""Chronological validation audit; data after 2026-10-26 15:15 UTC is untouched.

Methods: Raab et al. (2020) KSWIN; Qahtan et al. (2015) PCA-CD;
Barrabes et al. (2023) correlation permutation; Lukats et al. (2025)
window reset. This remains an exploratory validation, not final test.
"""
import csv, math, random, statistics
from pathlib import Path
from pilot_detectors import read_features, ks_statistic, pca_cd

ROOT=Path(__file__).resolve().parents[1]
CUTOFF='2026-10-26 15:15:00+00:00'
SEED=2015

def pearson(a,b):
    ma,mb=statistics.mean(a),statistics.mean(b)
    numerator=sum((x-ma)*(y-mb) for x,y in zip(a,b))
    denom=math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return numerator/denom if denom else float('nan')

def reset_kswin(stream,n=300,r=30,alpha=.0001):
    rng=random.Random(2020)
    buffer=[]
    alarms=[]
    threshold=math.sqrt(-math.log(alpha)/r)
    for i,(_,values) in enumerate(stream):
        buffer.append(values)
        if len(buffer)>n: buffer.pop(0)
        if len(buffer)<n: continue
        old=rng.sample(range(n-r),r)
        active=[j for j in range(3) if ks_statistic(
            [buffer[k][j] for k in old],
            [buffer[k][j] for k in range(n-r,n)])>threshold]
        if active:
            alarms.append((i,active))
            buffer=[]
    return alarms

def inject(validation,onset,kind,chosen,scale):
    rng=random.Random(SEED)
    out=[(t,list(v)) for t,v in validation]
    after=out[onset:]
    if kind in ('mean','combined'):
        for _,v in after:
            v[chosen]+=3*scale
    if kind in ('scale','combined'):
        for _,v in after:
            v[chosen]*=2
    if kind in ('correlation','combined'):
        column=[v[chosen] for _,v in after]
        rng.shuffle(column)
        for (_,v),value in zip(after,column):
            v[chosen]=value
    return [(t,tuple(v)) for t,v in out]

def metrics(before,after,col):
    x=[v[col] for _,v in before]
    y=[v[col] for _,v in after]
    return (statistics.mean(x),statistics.mean(y),
            statistics.pstdev(x),statistics.pstdev(y))

def main():
    all_rows=read_features(ROOT/'data'/'btc_15m.csv')
    historical=[x for x in all_rows if x[0]<=CUTOFF]
    assert len(historical)==2850
    train_raw=historical[:1995]
    val_raw=historical[1995:]
    centers=[statistics.mean(v[j] for _,v in train_raw) for j in range(3)]
    spreads=[statistics.stdev(v[j] for _,v in train_raw) for j in range(3)]
    assert all(s>0 for s in spreads)
    def standardize(rows):
        return [(t,tuple((v[j]-centers[j])/spreads[j] for j in range(3))) for t,v in rows]
    train=standardize(train_raw)
    val=standardize(val_raw)
    onset=len(val)//2
    selected=random.Random(SEED).randrange(3)
    scale=statistics.pstdev([v[selected] for _,v in train])
    cases={name:inject(val,onset,name,selected,scale)
           for name in ('mean','scale','correlation','combined')}
    lines=['# Pemeriksaan Validasi Kronologis','','Bukan hasil uji akhir.',
           f'Batas pelatihan: {train[-1][0]}',
           f'Validasi: {val[0][0]} sampai {val[-1][0]} ({len(val)} candle)',
           f'Awal injeksi: indeks {onset} ({val[onset][0]})',
           f'Fitur dipilih acak dengan seed {SEED}: {selected} (0 harga, 1 volume, 2 jumlah)',
           f'Simpangan baku fitur dari train: {scale:.6f}',
           '',
           'Fitur distandardisasi memakai rerata dan SD data latih awal (Jolliffe dan Cadima, 2016).',
           '## Pemeriksaan hasil injeksi',
           '| Skenario | Rerata sebelum | Rerata sesudah | SD sebelum | SD sesudah | Korelasi fitur 1 dan 2 sebelum | Korelasi sesudah |',
           '|---|---:|---:|---:|---:|---:|---:|']
    baseline=val[onset:]
    x0=[v[1] for _,v in baseline]; x2=[v[2] for _,v in baseline]
    corr0=pearson(x0,x2)
    for name,stream in cases.items():
        a,b,sa,sb=metrics(baseline,stream[onset:],selected)
        seg=stream[onset:]
        corr=pearson([v[1] for _,v in seg],[v[2] for _,v in seg])
        lines.append(f'| {name} | {a:.5f} | {b:.5f} | {sa:.5f} | {sb:.5f} | {corr0:.4f} | {corr:.4f} |')
        if name=='correlation':
            assert sorted(v[selected] for _,v in baseline)==sorted(v[selected] for _,v in seg)
    lines += ['','## Alarm KSWIN dengan pengosongan jendela',
              'Konfigurasi Raab: n=300, r=30, alpha per fitur=0,0001.',
              '| Aliran | Seluruh alarm | Alarm dalam 400 candle sesudah injeksi | Alarm sebelum injeksi |',
              '|---|---:|---:|---:|']
    for name,stream in [('asli',val),*cases.items()]:
        alarms=reset_kswin(stream)
        lines.append(f'| {name} | {len(alarms)} | {sum(onset<=i<=onset+400 for i,_ in alarms)} | {sum(i<onset for i,_ in alarms)} |')
    lines += ['','## Sensitivitas PCA-CD (histogram/CD-Area)',
              'Setiap pasangan w dan xi adalah kandidat validasi, bukan nilai dari paper.',
              'Ambang PH mengikuti persamaan pada Bagian 4.5 Qahtan.',
              '| w | xi | Aliran | Seluruh alarm | Alarm dalam 2w setelah injeksi |',
              '|---:|---:|---|---:|---:|']
    for w in (100,200):
        for xi in (1,5,10,25,100,500):
            for name,stream in [('asli',val),*cases.items()]:
                alarms=pca_cd(stream,w=w,xi=xi,mode='text_ph')['alarms']
                lines.append(f'| {w} | {xi} | {name} | {len(alarms)} | {sum(onset<=i<=onset+2*w for i,_ in alarms)} |')
    lines += ['','Jumlah alarm adalah titik deteksi. Data asli mungkin mengalami perubahan alami.',
              'Alarm di luar injeksi tidak otomatis berarti deteksi yang salah secara nyata.',
              'Sumber: https://doi.org/10.1016/j.neucom.2019.11.111 ; https://doi.org/10.1145/2783258.2783359 ; https://doi.org/10.1007/s41060-024-00620-y ; https://proceedings.neurips.cc/paper_files/paper/2023/hash/b3cd64ddad0a28da0f28a0e03a73ea7d-Abstract-Conference.html']
    out=ROOT/'reports'/'validation_detectors.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(out)
if __name__=='__main__':
    main()




