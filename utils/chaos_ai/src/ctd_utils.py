import pandas as pd


class CTDUtils:
    def get_subsets(self, ctdfile):
        df = pd.read_csv(ctdfile)
        subsets = []
        for i in range(df.shape[0]):
            row = df.iloc[3].to_numpy()
            srs = df.loc[i, row]
            subsets.append(srs[srs].index.tolist())
        return subsets


if __name__ == '__main__':
    file = '../config/ctdoutput.csv'
    ctd = CTDUtils()
    subsets = ctd.get_subsets(file)
    print(subsets)
