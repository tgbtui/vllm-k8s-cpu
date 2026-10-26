# vLLM (CPU) в Kubernetes

Qwen2.5-1.5B-Instruct на vLLM ≥ 0.27.0 (только CPU), rootless-образ, веса на PVC, секреты и конфиг через k8s.

## Требования (ПО и библиотеки)
- Docker, `kubectl` ≥ 1.27 (с встроенным kustomize), Minikube или любой k8s
- Доступ к интернету при сборке (GitHub, PyTorch CPU index, PyPI) и при первом старте пода (huggingface.co)
- Ресурсы: ≥ 4 vCPU, ≥ 12 ГБ RAM, 10 ГБ диска
- В образе: Ubuntu 24.04, Python 3.12, **vLLM 0.27.0** (собирается из тега `v0.27.0` под CPU), torch 2.13 (CPU); все зависимости зафиксированы в `docker/vllm/requirements.txt` (с хэшами)
- Downloader: Python 3.12 stdlib, без сторонних пакетов

## Структура
| Путь | Назначение |
|---|---|
| `k8s/` | манифесты + `kustomization.yaml` |
| `docker/vllm/Dockerfile` | rootless-образ (UID 10001), pinned deps |
| `docker/vllm/logging/` | кастомное логирование (`privacy_logging.py`, `logging_config.json`) |
| `docker/downloader/` | отдельный rootless-образ + `download_model.py` для initContainer |
| `scripts/lock-requirements.sh` | генерация полного `requirements.txt` с хэшами |
| `scripts/loadtest.py` | нагрузочный тест |

## Запуск (Minikube)
```bash
minikube start --cpus 6 --memory 14g
# 1) зафиксировать зависимости (один раз, результат коммитится)
./scripts/lock-requirements.sh
# 2) собрать образы прямо в Minikube
eval $(minikube docker-env)
docker build -f docker/vllm/Dockerfile       -t vllm-cpu:0.27.0 .
docker build -f docker/downloader/Dockerfile -t vllm-downloader:0.1.0 .
# 3) секреты (не храните реальные токены в git)
kubectl apply -f k8s/namespace.yaml
kubectl -n vllm create secret generic vllm-secrets \
  --from-literal=HF_TOKEN=hf_xxx --from-literal=VLLM_API_KEY=$(openssl rand -hex 24)
# 4) деплой (secret.yaml - лишь шаблон: уберите его из k8s/base/kustomization.yaml, если создали секрет командой выше)
kubectl apply -k k8s/
kubectl -n vllm logs -f deploy/vllm -c model-downloader   # 1-й старт: скачивание
kubectl -n vllm port-forward svc/vllm 8000:8000
curl localhost:8000/v1/chat/completions -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-1.5b-instruct","messages":[{"role":"user","content":"Привет!"}]}'
```
Смена настроек: правка `k8s/configmap.yaml` → `kubectl apply -k k8s/ && kubectl -n vllm rollout restart deploy/vllm` (пересборка не нужна).

## Как выполнены требования
- **CPU-only, vLLM ≥ 0.27.0:** сборка `VLLM_TARGET_DEVICE=cpu` из `v0.27.0`; квантизация не используется (bf16), параметр `QUANTIZATION` в ConfigMap.
- **Rootless:** `USER 10001` в обоих образах + `runAsNonRoot`, `drop ALL`, `allowPrivilegeEscalation: false`, `fsGroup` для PVC.
- **Pinned deps:** `requirements.txt` с `--hash`; Dockerfile падает, если файл не залочен; `pip --require-hashes --no-deps`.
- **Приватное логирование:** `VLLM_LOGGING_CONFIG_PATH` → handler-фильтр `PrivacyFilter` заменяет дампы запроса/ответа на `request received id=… tokens=N [content redacted]`; `--enable-log-requests` не используется; факт обращения логируется (плюс access-лог uvicorn). Тест: `python3 -c "import sys;sys.path.insert(0,'tests');import test_privacy_logging as t;t.test_no_prompt_or_response_leak()"`.
- **PVC-кэш:** initContainer качает в `/models` и пишет маркер `.download_complete`; при рестартах сети нет (основной контейнер с `HF_HUB_OFFLINE=1`, том `readOnly`).
- **Secret:** `HF_TOKEN` (только initContainer), `VLLM_API_KEY` (Bearer; vLLM читает из env, в `ps` не виден).
- **ConfigMap:** все параметры запуска (`entrypoint.sh` собирает аргументы).
- **Бонусы:** kustomize (`kubectl apply -k k8s/`), отдельный initContainer-образ, нагрузочный тест.

## Нагрузочное тестирование
```bash
kubectl -n vllm port-forward svc/vllm 8000:8000 &
python3 scripts/loadtest.py --api-key $KEY --concurrency 2 --requests 8 --max-tokens 64 --long-words 500
```
Скрипт (`scripts/loadtest.py`, stdlib) шлёт streaming-запросы `/v1/chat/completions` и считает TTFT, latency (avg/p95) и throughput (сгенерированные токены / время теста).

**Стенд:** MacBook Air M4, Docker Desktop (Linux VM) + Minikube (6 vCPU, 11 ГБ), Qwen2.5-1.5B-Instruct, bf16, `--enforce-eager`, `MAX_MODEL_LEN=2048`, `MAX_NUM_SEQS=4`, `max_tokens=64`, 8 запросов, конкурентность 2. Короткий промпт ≈ 12 токенов, длинный - 500 слов (≈1000-1500 токенов). Это CPU в виртуальной машине: абсолютные цифры нужно сравнивать только между собой.

| prompt | conc | ok/err | TTFT avg, s | TTFT p95, s | latency avg, s | latency p95, s | throughput, tok/s | req/s |
|---|---|---|---|---|---|---|---|---|
| short (~12 tok) | 2 | 8/0 | 1.14 | 1.84 | 6.81 | 7.30 | 10.3 | 0.29 |
| long (~1000+ tok) | 2 | 8/0 | 6.07 | 18.72 | 8.47 | 20.73 | 3.1 | 0.24 |

Вывод: на коротких промптах TTFT ≈ 1 с, время почти целиком уходит на decode (~10 ток/с на 2 потока). На длинных TTFT растёт в ~5 раз (prefill упирается в CPU), а p95 TTFT - в ~10 раз из-за очереди prefill двух запросов; throughput по генерации падает втрое. Приёмочный тест `scripts/smoke_test.sh`: 6/6 PASS.

## Аналитика: что менять для throughput
Рекомендации опираются на документацию vLLM (параметры планировщика и CPU-бэкенда) и данные таблицы выше (рост TTFT на длинных промптах); сами параметры отдельно не замерялись.

**A) Много запросов, мало токенов (decode-bound).** Растёт `MAX_NUM_SEQS` (больше одновременных последовательностей в батче; decode на CPU упирается в память, батч amortizes чтение весов), достаточный `VLLM_CPU_KVCACHE_SPACE`, чтобы все последовательности поместились; `ENABLE_PREFIX_CACHING=true` при повторяющемся системном промпте; `VLLM_CPU_OMP_THREADS_BIND` на физические ядра одного NUMA-узла (без HT), CPU requests=limits; горизонтально - больше реплик. `MAX_MODEL_LEN` можно уменьшить, чтобы не резервировать лишнее.

**Б) Мало запросов, огромный контекст (prefill-bound).** Включить chunked prefill и поднять `MAX_NUM_BATCHED_TOKENS` (крупные чанки prefill лучше загружают ядра; слишком большое значение ухудшает TTFT/latency других запросов); `MAX_NUM_SEQS` снизить (контекст дорогой - KV-кэш делится между меньшим числом запросов); увеличить `MAX_MODEL_LEN` и `VLLM_CPU_KVCACHE_SPACE` под реальный контекст; prefix caching для общих префиксов (RAG/документ); bf16/INT8-квантизация снижает нагрузку на память и вычисления.

## Ограничения
- Проверено на MacBook M4 (Docker Desktop + Minikube): сборка, деплой, приёмочный тест и нагрузка.
- В runtime-образе есть `g++` и `python3-dev`: PyTorch компилирует код на CPU при первом запросе (первый запрос медленнее). Профиль `macos-m4` использует `--enforce-eager`, `bfloat16`, KV-кэш 1 ГиБ.
- `requirements.txt` генерируется `scripts/lock-requirements.sh` (хэши привязаны к архитектуре сборки).
- Для NUMA-оптимизаций vLLM CPU может требовать `SYS_NICE`/ослабленный seccomp - добавьте в `securityContext` при необходимости.

## macOS (Apple Silicon, M4)
Docker Desktop (Resources: ≥6 CPU, ≥12 ГБ RAM) → `minikube start --driver=docker --cpus=6 --memory=11g`.
Сборка нативная arm64 (без `--platform linux/amd64`), деплой с профилем для Mac:
```bash
kubectl apply -k k8s/overlays/macos-m4     # float32, MAX_MODEL_LEN=2048, KV 2 GiB, SYS_NICE
```
BF16 в Linux-VM на M4 можно включить через `DTYPE: "bfloat16"` в ConfigMap после первого успешного запуска.

## Приёмочный тест
```bash
kubectl -n vllm port-forward svc/vllm 8000:8000 &
KEY=<VLLM_API_KEY> ./scripts/smoke_test.sh
```
Проверяет: /health, 401 без токена, ответ с токеном, отсутствие промпта и ответа в логах, запись факта запроса, загрузку из PVC после рестарта.
