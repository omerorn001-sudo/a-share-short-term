import pickle
sv=pickle.load(open("fund_hist_h1.pkl","rb"))["sv"]; print("sv",len(sv),sv.NOTICE_DATE.min(),sv.NOTICE_DATE.max())
for f in ("fund_hist_jj.pkl","fund_hist_aug.pkl","fund_hist.pkl"):
    d=pickle.load(open(f,"rb")); d["sv"]=sv; pickle.dump(d,open(f,"wb"))
