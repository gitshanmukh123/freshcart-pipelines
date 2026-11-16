# FreshCart Pipelines - From Git to Gold

A reproducible course project covering Git/GitHub Actions, a Snowflake
Bronze-to-Gold ELT pipeline, a Mage Iris pipeline, a RabbitMQ topic exchange with
driver consumers, and an optional RabbitMQ-to-lakehouse bonus.

> The FreshCart notebook is a sanitized copy of the classroom workbook: outputs
> and classroom credentials were removed, and the B3/B4/B5 changes are student
> work. The Mage blocks follow the classroom Iris pipeline. See
> `ASSUMPTIONS.md` for the remaining assumptions.

## Repository map

```text
freshcart-pipelines/
├── .github/workflows/ci.yml          # Python 3.12 + pytest CI
├── elt/
│   ├── freshcart_data.py             # reconstructed 8-row fixture + CRM/FX
│   ├── freshcart_lib.py              # Snowflake SQL, helpers, local checks
│   └── freshcart_elt.ipynb           # runnable Colab/Snowflake notebook
├── iris_project/                     # Mage project
│   ├── data_loaders/load_iris.py
│   ├── transformers/prepare_data.py
│   ├── transformers/validate_data.py
│   ├── transformers/train_model.py
│   ├── transformers/evaluate_model.py
│   ├── data_exporters/save_results.py
│   └── pipelines/iris_classifier/metadata.yaml
├── stream/
│   ├── common.py                     # topic matching + broker helpers
│   ├── dispatcher.py                 # Rapido event producer
│   ├── driver.py                     # ACK/NACK consumer
│   ├── order_producer.py             # bonus FreshCart producer
│   └── lakehouse_consumer.py         # bonus persist-before-ACK consumer
├── tests/                            # local tests
├── tools/build_freshcart_notebook.py
├── requirements.txt                  # CI/local test dependencies
├── requirements-colab.txt
├── requirements-mage.txt
├── ASSUMPTIONS.md
├── EXECUTION_GUIDE.md
├── EVIDENCE.md
└── README.md
```


