"""Exploratory configuration sweep on the frozen Kraken pilot period."""
import argparse
import csv
import math
import os
import random
import statistics
import time
from pathlib import Path

from pilot_detectors import ks_statistic, pca_cd, read_features
from pilot_models import THRESHOLD, anomaly_score, rf_predict, train_if, train_rf
from validation_detectors import CUTOFF, inject, pearson, reset_kswin

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("TUNING_DATA_ROOT", ROOT))
OUTPUT_ROOT = Path(os.environ.get("TUNING_OUTPUT_ROOT", ROOT))
# Sensitivity analysis, not a claim that one delay is universally correct.
# Cerqueira et al. (2026), Table 3, choose dataset-specific limits. Their
# limits span roughly 2.5%-10.8% of each dataset. On 855 validation candles,
# 25/50/85 cover that range; 100/200/400 expose sensitivity to looser rules.
HORIZONS = (25, 50, 85, 100, 200, 400)
DISPLAY_HORIZON = 85

def configs():
    for n in (150, 200, 250, 300, 350, 400, 450, 500):
        for r in (30, 60, 90, 120):
            if n >= 2*r:
                for alpha in (.0001, .001, .01/3):
                    yield ("KSWIN", n, r, alpha)
    for n in (400, 450, 500, 550, 600):
        for r in (60, 90, 120, 150):
            for alpha in (.01, .05/3, .1/3):
                yield ("KSWIN", n, r, alpha)
    for w in (100, 125, 150, 175, 200, 225, 250, 275, 300):
        for xi in (0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
            yield ("PCA-CD", w, xi, .005)

def audit_injections(val,cases,feature,scale):
    """Check empirical changes before any detector configuration is scored."""
    audited=[]
    for kind,onset,stream in cases[1:]:
        original=val[onset:]
        changed=stream[onset:]
        x=[v[feature] for _,v in original]
        y=[v[feature] for _,v in changed]
        mean0,mean1=statistics.mean(x),statistics.mean(y)
        sd0,sd1=statistics.pstdev(x),statistics.pstdev(y)
        other=1 if feature!=1 else 0
        paired=[v[other] for _,v in original]
        corr0,corr1=pearson(paired,x),pearson(paired,y)
        lag0,lag1=pearson(x[:-1],x[1:]),pearson(y[:-1],y[1:])
        length=min(100,len(x))
        local_ks=ks_statistic(x[:length],y[:length])
        close=lambda a,b:math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9)
        if kind=="mean":
            assert close(mean1-mean0,3*scale) and close(sd1,sd0)
            assert close(corr1,corr0)
        elif kind=="scale":
            assert close(mean1,mean0) and close(sd1,2*sd0)
            assert close(corr1,corr0)
        elif kind=="correlation":
            assert sorted(x)==sorted(y) and close(mean1,mean0)
            assert close(sd1,sd0) and not close(corr1,corr0)
        elif kind=="combined":
            assert close(mean1-mean0,3*scale) and close(sd1,2*sd0)
            assert not close(corr1,corr0)
        audited.append(dict(scenario=kind,onset=onset,count=len(x),
                            mean_before=mean0,mean_after=mean1,
                            sd_before=sd0,sd_after=sd1,
                            correlation_before=corr0,correlation_after=corr1,
                            lag1_before=lag0,lag1_after=lag1,
                            local_ks_first_100=local_ks))
    return audited

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
    injection_audit=audit_injections(val,cases,feature,scale)
    for a in injection_audit:
        print("INJECTION_AUDIT",a,flush=True)
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
                history=train[-(a-1):]
                alarms=[i-len(history) for i,_ in reset_kswin(history+stream,n=a,r=b,alpha=c)
                        if i>=len(history)]
            else:
                history=train[-(2*a-1):]
                alarms=[i-len(history) for i,_ in pca_cd(history+stream,w=a,xi=b,delta=c,
                        mode="text_ph")["alarms"] if i>=len(history)]
            det_sec=time.perf_counter()-start
            row=dict(config=name,method=method,param1=a,param2=b,param3=c,
                     scenario=kind,onset=onset,alarm_count=len(alarms),
                     detector_seconds=det_sec,alarm_indices=";".join(map(str,alarms)))
            for horizon in HORIZONS:
                matched=[i for i in alarms if onset>=0 and
                         onset<=i<=min(onset+horizon,len(stream)-1)]
                tp=int(bool(matched))
                row[f"matched_h{horizon}"]=tp
                row[f"unmatched_h{horizon}"]=len(alarms)-tp
                row[f"missed_h{horizon}"]=int(onset>=0 and not matched)
                row[f"delay_h{horizon}"]=min(matched)-onset if matched else ""
            if not skip_rf:row.update(evaluate_rf(kind,onset,stream,alarms))
            rows.append(row)
            runs.append(row)
        injected=rows[1:]
        item=dict(config=name,method=method,param1=a,param2=b,param3=c,
                  control_alarms=rows[0]["alarm_count"],
                  same_alarm_pattern_as_control=sum(
                      x["alarm_indices"]==rows[0]["alarm_indices"] for x in injected),
                  detector_seconds=sum(x["detector_seconds"] for x in rows),
                  retrains=sum(x["alarm_count"] for x in injected))
        for horizon in HORIZONS:
            tp=sum(x[f"matched_h{horizon}"] for x in injected)
            fp=sum(x[f"unmatched_h{horizon}"] for x in injected)
            fn=sum(x[f"missed_h{horizon}"] for x in injected)
            p=tp/(tp+fp) if tp+fp else 0
            r=tp/(tp+fn) if tp+fn else 0
            f=2*p*r/(p+r) if p+r else 0
            delays=[x[f"delay_h{horizon}"] for x in injected
                    if x[f"delay_h{horizon}"]!=""]
            item.update({f"tp_h{horizon}":tp,f"fp_h{horizon}":fp,
                         f"fn_h{horizon}":fn,f"precision_h{horizon}":p,
                         f"recall_h{horizon}":r,f"f1_h{horizon}":f,
                         f"mean_delay_h{horizon}":statistics.mean(delays)
                         if delays else ""})
        if not skip_rf:
            for metric in ("rf_accuracy","rf_precision","rf_recall","rf_f1"):
                item["mean_"+metric]=statistics.mean(x[metric] for x in injected)
            item["control_rf_f1"]=rows[0]["rf_f1"]
        summary.append(item)
        h=DISPLAY_HORIZON
        print(f"{len(summary)}/{len(all_configs)} {name} F1@{h}={item[f'f1_h{h}']:.3f} TP={item[f'tp_h{h}']} FP={item[f'fp_h{h}']} FN={item[f'fn_h{h}']} control={item['control_alarms']} same_pattern={item['same_alarm_pattern_as_control']}/8 rf_F1={item.get('mean_rf_f1', '')}",flush=True)
    out=OUTPUT_ROOT/"reports"
    save_csv(out/"tuning_sweep_runs.csv",runs)
    save_csv(out/"tuning_sweep_summary.csv",summary)
    h=DISPLAY_HORIZON
    ordered=sorted(summary,key=lambda x:(-x[f"f1_h{h}"],x["control_alarms"],
                       x[f"mean_delay_h{h}"] if x[f"mean_delay_h{h}"]!="" else math.inf))
    lines=["# Pencarian konfigurasi pada data uji awal","",
           "Eksplorasi Plan A, bukan hasil uji akhir. Data dibekukan hingga "+CUTOFF+".",
           "Latih=1995, validasi=855 candle. Titik injeksi 285 dan 427.",
           "Jendela awal diisi dari ujung data latih: n-1 catatan untuk KSWIN dan",
           "2w-1 catatan untuk PCA-CD. Alarm dilaporkan hanya pada validasi.",
           "Empat skenario yang diperiksa digunakan pada kedua titik. Delapan aliran injeksi",
           "berasal dari data yang sama dan bukan delapan dataset independen.",
           "Skenario rerata, simpangan baku, dan korelasi mengadaptasi jenis perubahan",
           "Qahtan et al. (2015), bukan mereplikasi generator Gaussian mereka.",
           "Pergeseran waktu siklik pada satu fitur menjaga sebaran seluruh segmen",
           "dan sebagian besar pasangan waktu berturutan. Ini hanya adaptasi",
           "permutasi fitur Barrabés et al. (2023) dan gagasan time-shift surrogate",
           "pada data deret waktu; bukan prosedur identik dari kedua paper.",
           "Batas putaran dan distribusi dalam jendela pendek tetap dapat berubah.",
           "Karena itu skenario 'correlation' berarti pergeseran hubungan",
           "antarfitur yang juga mungkin mengubah sebaran lokal, bukan",
           "perubahan korelasi murni pada seluruh jendela bergerak.",
           "Satu alarm dipasangkan dengan paling banyak satu injeksi.",
           "FP di sini berarti alarm tanpa pasangan injeksi, bukan kesalahan pasar yang terbukti.",
           "Batas keterlambatan diuji pada 25, 50, 85, 100, 200, dan 400 candle.",
           "Menurut Cerqueira et al. (2026), batas ditentukan sesuai panjang data.",
           "Pada 855 candle, 25-85 meliputi kira-kira 2,9%-9,9%;",
           "100-400 memperlihatkan dampak aturan yang lebih longgar.",
           "Tabel diurutkan menurut F1 pada 85 candle hanya agar mudah dibaca.",
           "Ini bukan pemilihan konfigurasi otomatis. Periksa pula alarm pada data",
           "asli, pola alarm yang sama, hasil tiap skenario, dan seluruh batas.","",
           "## Audit injeksi sebelum pengujian","",
           "| Skenario | Onset | Rerata awal→akhir | SD awal→akhir | Korelasi awal→akhir | Lag-1 awal→akhir | KS 100 awal |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for a in injection_audit:
        lines.append(f"| {a['scenario']} | {a['onset']} | {a['mean_before']:.3f}→{a['mean_after']:.3f} | {a['sd_before']:.3f}→{a['sd_after']:.3f} | {a['correlation_before']:.3f}→{a['correlation_after']:.3f} | {a['lag1_before']:.3f}→{a['lag1_after']:.3f} | {a['local_ks_first_100']:.3f} |")
    lines += ["","## Ringkasan seluruh konfigurasi","",
           "| Konfigurasi | Alarm asli | Pola sama / 8 | TP/FP/FN @85 | F1 @25/50/85/100/200/400 | Delay @85 | F1 RF | Retrain |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in ordered:
        rf=f"{x['mean_rf_f1']:.3f}" if not skip_rf else "—"
        delay=f"{x[f'mean_delay_h{h}']:.1f}" if x[f"mean_delay_h{h}"]!="" else "—"
        scores="/".join(f"{x[f'f1_h{d}']:.3f}" for d in HORIZONS)
        lines.append(f"| {x['config']} | {x['control_alarms']} | {x['same_alarm_pattern_as_control']} | {x[f'tp_h{h}']}/{x[f'fp_h{h}']}/{x[f'fn_h{h}']} | {scores} | {delay} | {rf} | {x['retrains']} |")
    lines+=["","Semua metrik dan waktu ada dalam tuning_sweep_summary.csv.",
            "Rincian tiap aliran dan indeks alarm ada dalam tuning_sweep_runs.csv.",
            "KSWIN memvariasikan n, r, dan alpha per fitur. PCA-CD memvariasikan",
            "w dan xi; delta tetap 0,005. Kandidat adalah protokol eksplorasi,",
            "bukan angka yang diwajibkan paper.",
            "Sumber: https://doi.org/10.1145/2783258.2783359 ;",
            "https://arxiv.org/html/2606.07789 ;",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC11398661/ ;",
            "https://proceedings.neurips.cc/paper_files/paper/2023/file/b3cd64ddad0a28da0f28a0e03a73ea7d-Paper-Conference.pdf",""]
    (out/"tuning_sweep.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"Finished: {len(summary)} configurations; {len(rf_cache)} RF runs")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--limit-configs",type=int)
    parser.add_argument("--skip-rf",action="store_true")
    parser.add_argument("--method",choices=("KSWIN","PCA-CD"))
    args=parser.parse_args()
    main(args.limit_configs,args.skip_rf,args.method)


