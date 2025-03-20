from illufly.datasets.loader import NL2SQLDatasetLoader

def main():
    loader = NL2SQLDatasetLoader()
    nl2sql_cn_data = loader.load_dataset("nl2sql-cn")
    if nl2sql_cn_data is not None:
        print(nl2sql_cn_data.head())

if __name__ == "__main__":
    main()