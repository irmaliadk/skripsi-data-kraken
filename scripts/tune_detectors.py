"""Exploratory configuration sweep on the frozen Kraken pilot period."""
import argparse
import csv
import math
import os
import random
import statistics
import time
from pathlib import Path

from pilot_detectors import pca_cd, read_features
from pilot_models import THRESHOLD, anomaly_score, rf_predict, train_if, train_rf
from validation_detectors import CUTOFF, inject, reset_kswin

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("TUNING_DATA_ROOT", ROOT))
OUTPUT_ROOT = Path(os.environ.get("TUNING_OUTPUT_ROOT", ROOT))
HORIZON = 400

def configs():
    for n in (150, 200, 300, 400):
        for r in (30, 60, 90):
            if n >= 2*r:
                for alpha in (.0001, .001, .01/3):
                    yield ("KSWIN", n, r, alpha)
    for w in (100, 150, 200, 300):
        for xi in (1, 2, 5, 10):
            yield ("PCA-CD", w, xi, .005)

def confusion(y, pred):
    tp=sum(a == b == 1 for a,b in zip(y,pred))
    fp=sum(a == 0 and b == 1 for a,b in zip(y,pred))
    fn=sum(a == 1 and b == 0 for a,b in zip(y,pred))
    tn=len(y)-tp-fp-fn
    p=tp/(tp+fp) if tp+fp else 0
    r=tp/(tp+fn) if tp+fn else 0
    f=2*p*r/(p+r) if p+r else 0
    return dict(rf_tp=tp,rf_fp=fp,rf_fn=fn,rf_tn=tn,
                rf_accuracy=(tp+tn)/len(y),rf_precision=p,rf_recall=r,rf_f1=f)

def save_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as h:
        writer=csv.DictWriter(h,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main(limit,skip_rf,method_filter):
    data=[z for z in read_features(DATA_ROOT/"data"/"btc_15m.csv") if z[0]<=CUTOFF]
    if len(data)!=2850:
        raise ValueError(f"Frozen data changed: expected 2850, got {len(data)}")
    raw_train,raw_val=data[:1995],data[1995:]
    mu=[statistics.mean(v[j] for _,v in raw_train) for j in range(3)]
    sd=[statistics.stdev(v[j] for _,v in raw_train) for j in range(3)]
    def standard(rows):
        return [(t,tuple((v[j]-mu[j])/sd[j] for j in range(3))) for t,v in rows]
    train,val=standard(raw_train),standard(raw_val)
    feature=random.Random(2015).randrange(3)
    scale=statistics.pstdev(v[feature] for _,v in train)
    cases=[("original",-1,val)]
    for onset in (len(val)//3,len(val)//2):
        for kind in ("mean","scale","correlation","combined"):
            cases.append((kind,onset,inject(val,onset,kind,feature,scale)))
    forest_if=train_if([v for _,v in train])
    initial=[(v,int(anomaly_score(forest_if,v)>=THRESHOLD)) for _,v in train]
    first_rf=train_rf(initial)
    labels={(kind,onset):[int(anomaly_score(forest_if,v)>=THRESHOLD) for _,v in stream]
            for kind,onset,stream in cases}
    rf_cache={}
    def evaluate_rf(kind,onset,stream,alarm_indices):
        key=(kind,onset,tuple(alarm_indices))
        if key in rf_cache:return rf_cache[key]
        y=labels[kind,onset]
        model=first_rf
        observed=[]
        pred=[]
        alarm_set=set(alarm_indices)
        for i,(_,v) in enumerate(stream):
            pred.append(rf_predict(model,v))
            observed.append((v,y[i]))
            if i in alarm_set:
                model=train_rf(initial+observed)
        result=confusion(y,pred)
        rf_cache[key]=result
        return result
    all_configs=[c for c in configs() if method_filter is None or c[0]==method_filter]
    if limit is not None:all_configs=all_configs[:limit]
    runs=[]
    summary=[]
    for config in all_configs:
        method,a,b,c=config
        name=f"{method}:{a}:{b}:{c:.9g}"
        rows=[]
        for kind,onset,stream in cases:
            start=time.perf_counter()
            if method=="KSWIN":
                alarms=[i for i,_ in reset_kswin(stream,n=a,r=b,alpha=c)]
            else:
                alarms=[i for i,_ in pca_cd(stream,w=a,xi=b,delta=c,mode="text_ph")["alarms"]]
            det_sec=time.perf_counter()-start
            matched=[i for i in alarms if onset>=0 and onset<=i<=min(onset+HORIZON,len(stream)-1)]
            tp=int(bool(matched))
            row=dict(config=name,method=method,param1=a,param2=b,param3=c,
                     scenario=kind,onset=onset,alarm_count=len(alarms),
                     matched=tp,unmatched=len(alarms)-tp,
                     missed=int(onset>=0 and not matched),
                     delay=min(matched)-onset if matched else "",
                     detector_seconds=det_sec,alarm_indices=";".join(map(str,alarms)))
            if not skip_rf:row.update(evaluate_rf(kind,onset,stream,alarms))
            rows.append(row)
            runs.append(row)
        injected=rows[1:]
        tp=sum(x["matched"] for x in injected)
        fp=sum(x["unmatched"] for x in injected)
        fn=sum(x["missed"] for x in injected)
        p=tp/(tp+fp) if tp+fp else 0
        r=tp/(tp+fn) if tp+fn else 0
        f=2*p*r/(p+r) if p+r else 0
        delays=[x["delay"] for x in injected if x["delay"]!=""]
        item=dict(config=name,method=method,param1=a,param2=b,param3=c,
                  control_alarms=rows[0]["alarm_count"],tp=tp,fp=fp,fn=fn,
                  detector_precision=p,detector_recall=r,detector_f1=f,
                  mean_delay=statistics.mean(delays) if delays else "",
                  max_delay=max(delays) if delays else "",
                  detector_seconds=sum(x["detector_seconds"] for x in rows),
                  retrains=sum(x["alarm_count"] for x in injected))
        if not skip_rf:
            for metric in ("rf_accuracy","rf_precision","rf_recall","rf_f1"):
                item["mean_"+metric]=statistics.mean(x[metric] for x in injected)
            item["control_rf_f1"]=rows[0]["rf_f1"]
        summary.append(item)
        print(f"{len(summary)}/{len(all_configs)} {name} det_F1={f:.3f}",flush=True)
    out=OUTPUT_ROOT/"reports"
    save_csv(out/"tuning_sweep_runs.csv",runs)
    save_csv(out/"tuning_sweep_summary.csv",summary)
    ordered=sorted(summary,key=lambda x:(-x["detector_f1"],x["control_alarms"],
                       x["mean_delay"] if x["mean_delay"]!="" else math.inf))
    lines=["# Pencarian konfigurasi pada data uji awal","",
           "Eksplorasi Plan A, bukan hasil uji akhir. Data dibekukan hingga "+CUTOFF+".",
           "Latih=1995, validasi=855 candle. Titik injeksi 285 dan 427.",
           "Empat skenario lama digunakan pada kedua titik. Delapan aliran injeksi",
           "berasal dari data yang sama dan bukan delapan dataset independen.",
           "Satu alarm dapat dicocokkan dengan paling banyak satu injeksi dalam 400 candle.",
           "FP berarti alarm tanpa pasangan injeksi, bukan kesalahan pasar yang terbukti.",
           "Urutan tabel berdasarkan F1 detektor hanya untuk dibaca, bukan memilih otomatis.","",
           "| Konfigurasi | Alarm asli | TP/FP/FN | F1 | Delay | F1 RF | Retrain |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for x in ordered:
        rf=f"{x['mean_rf_f1']:.3f}" if not skip_rf else "—"
        delay=f"{x['mean_delay']:.1f}" if x["mean_delay"]!="" else "—"
        lines.append(f"| {x['config']} | {x['control_alarms']} | {x['tp']}/{x['fp']}/{x['fn']} | {x['detector_f1']:.3f} | {delay} | {rf} | {x['retrains']} |")
    lines+=["","Semua metrik dan waktu ada dalam tuning_sweep_summary.csv.",
            "Rincian tiap aliran dan indeks alarm ada dalam tuning_sweep_runs.csv.",
            "KSWIN memvariasikan n, r, dan alpha per fitur. PCA-CD memvariasikan",
            "w dan xi; delta tetap 0,005. Kandidat adalah protokol eksplorasi,",
            "bukan angka yang diwajibkan paper.",""]
    (out/"tuning_sweep.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"Finished: {len(summary)} configurations; {len(rf_cache)} RF runs")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--limit-configs",type=int)
    parser.add_argument("--skip-rf",action="store_true")
    parser.add_argument("--method",choices=("KSWIN","PCA-CD"))
    args=parser.parse_args()
    main(args.limit_configs,args.skip_rf,args.method)

