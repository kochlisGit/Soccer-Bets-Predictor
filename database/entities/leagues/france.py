from database.entities.leagues.league import League


class Ligue1(League):
    def __init__(self):
        super().__init__(
            country='France',
            name='Ligue-1',
            year_start=2005,
            category='main',
            data_url='https://www.football-data.co.uk/mmz4281/{}/F1.csv',
            fixtures_url='https://footystats.org/france/ligue-1/fixtures'
        )


class Ligue2(League):
    def __init__(self):
        super().__init__(
            country='France',
            name='Ligue-2',
            year_start=2005,
            category='main',
            data_url='https://www.football-data.co.uk/mmz4281/{}/F2.csv',
            fixtures_url='https://footystats.org/france/ligue-2/fixtures'
        )
