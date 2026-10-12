cd /data/tmp/bt; export KP=/data/tmp/bt/kpanel260.pkl
run(){ for s in "$@"; do python3 run_bt_$s.py && python3 feats_$s.py || echo FAIL $s; done; }
run jan feb mar apr may > p1.log 2>&1 &
run jun jul aug > p2.log 2>&1 &
wait; KP=/data/tmp/bt/kpanel.pkl python3 run_bt.py && KP=/data/tmp/bt/kpanel.pkl python3 feats.py; echo PIPE_DONE
