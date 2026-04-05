# install

python version: 3.12

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PYTHONPATH:$PWD/conware
```


# run

模型生成和优化

```bash
./conware/bin/conware-model-generate firmware/custom/blink
./conware/bin/conware-model-optimize firmware/custom/blink/model.pickle
```


模拟执行

```bash
./conware/bin/conware-emulate firmware/custom/blink/blink.ino.bin -r firmware/custom/blink --sleep_time 30 
./conware/bin/conware-emulate firmware/custom/blink/blink.ino.bin -r firmware/custom/blink --sleep_time 30 -m ./firmware/custom/blink/model_optimized.pickle
```