"""End-to-end chronological validation only; later data is reserved as test.
All IF, RF, KSWIN, PCA-CD implementations use local from-scratch code.
"""
import random, statistics
from pathlib import Path
from pilot_detectors import read_features,pca_cd
from validation_detectors import CUTOFF,SEED,inject,reset_kswin
from pilot_models import train_if,anomaly_score,train_rf,rf_predict,THRESHOLD

ROOT=Path(__file__).resolve().parents[1]

def confusion(y,p):
    tp=sum(a==1 and b==1 for a,b in zip(y,p))
    fp=sum(a==0 and b==1 for a,b in zip(y,p))
    fn=sum(a==1 and b==0 for a,b in zip(y,p))
    tn=sum(a==0 and b==0 for a,b in zip(y,p))
    precision=tp/(tp+fp) if tp+fp else 0
    recall=tp/(tp+fn) if tp+fn else 0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0
    return f'TP={tp}, FP={fp}, FN={fn}, TN={tn}, P={precision:.4f}, R={recall:.4f}, F1={f1:.4f}'

def main():
    all_rows=[x for x in read_features(ROOT/'data'/'btc_15m.csv') if x[0]<=CUTOFF]
    assert len(all_rows)==2850
    train_raw=all_rows[:1995]
    validation_raw=all_rows[1995:]
    centers=[statistics.mean(x[1][j] for x in train_raw) for j in range(3)]
    scales=[statistics.stdev(x[1][j] for x in train_raw) for j in range(3)]
    def standard(rows):
        return [(t,tuple((v[j]-centers[j])/scales[j] for j in range(3))) for t,v in rows]
    train=standard(train_raw)
    val=standard(validation_raw)
    forest_if=train_if([v for _,v in train])
    initial=[(v,int(anomaly_score(forest_if,v)>=THRESHOLD)) for _,v in train]
    first_rf=train_rf(initial)
    onset=len(val)//2
    selected=random.Random(SEED).randrange(3)
    lines=['# Uji alur lengkap pada validasi kronologis','',
           '**Bukan hasil pengujian akhir.**',
           f'Batas data historis: {CUTOFF}; latih={len(train)}, validasi={len(val)}, awal injeksi={onset}.',
           'Urutan setiap candle: prediksi RF -> skor IF -> alarm detektor -> RF dilatih ulang jika alarm.',
           'PCA-CD: w=200, delta=0,005, xi=5; KSWIN: n=300, r=30, alpha=0,0001.',
           'Pembaruan RF menggunakan data latih awal dan seluruh candle validasi yang telah lewat.',
           '',
           '| Skenario | Jalur | Jumlah alarm | Jumlah pelatihan ulang | Kinerja terhadap label semu IF |',
           '|---|---|---:|---:|---|']
    for name,stream in [('asli',val)]+[(k,inject(val,onset,k,selected,1.0))
                                   for k in ('mean','scale','correlation','combined')]:
        alarms_ks={i for i,_ in reset_kswin(stream)}
        alarms_pca={i for i,_ in pca_cd(stream,w=200,xi=5,mode='text_ph')['alarms']}
        y=[int(anomaly_score(forest_if,v)>=THRESHOLD) for _,v in stream]
        for lane,alarms in [('tanpa',set()),('KSWIN',alarms_ks),('PCA-CD',alarms_pca)]:
            model=first_rf
            observed=[]
            predictions=[]
            retrains=0
            for i,(_,v) in enumerate(stream):
                predictions.append(rf_predict(model,v))
                observed.append((v,y[i]))
                if i in alarms:
                    model=train_rf(initial+observed)
                    retrains+=1
            lines.append(f'| {name} | {lane} | {len(alarms)} | {retrains} | {confusion(y,predictions)} |')
    lines += ['','Perbandingan ini hanya mengukur kesesuaian terhadap label semu IF, bukan fraud terverifikasi.']
    out=ROOT/'reports'/'validation_pipeline.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(out)
if __name__=='__main__':main()

