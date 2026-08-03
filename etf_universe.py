"""可交易 ETF 池：每类保留少量高流动性代表，避免把同质产品全塞进模型。"""

ETF_UNIVERSE = {
    # A股宽基 / 风格
    'sh510050': {'name': '上证50ETF', 'code': '510050', 'sector': '大盘价值', 'group': 'large_cap', 'risk_on': 1, 'keywords': ['上证50', '大盘', '蓝筹', '价值']},
    'sh510300': {'name': '沪深300ETF', 'code': '510300', 'sector': '宽基', 'group': 'large_cap', 'risk_on': 1, 'keywords': ['沪深300', '大盘', '宽基']},
    'sh510500': {'name': '中证500ETF', 'code': '510500', 'sector': '中盘', 'group': 'mid_cap', 'risk_on': 1, 'keywords': ['中证500', '中盘', '中小盘']},
    'sh512100': {'name': '中证1000ETF', 'code': '512100', 'sector': '小盘', 'group': 'small_cap', 'risk_on': 1, 'keywords': ['中证1000', '小盘', '微盘']},
    'sh510880': {'name': '红利ETF', 'code': '510880', 'sector': '红利', 'group': 'dividend', 'risk_on': 1, 'keywords': ['红利', '高股息', '股息']},
    'sh512890': {'name': '红利低波ETF', 'code': '512890', 'sector': '红利低波', 'group': 'dividend', 'risk_on': 1, 'keywords': ['红利低波', '低波', '高股息']},

    # 行业 / 主题
    'sh512760': {'name': '半导体ETF', 'code': '512760', 'sector': '半导体', 'group': 'chips', 'risk_on': 1, 'keywords': ['半导体', '芯片', '集成电路', '国产替代']},
    'sz159995': {'name': '芯片ETF', 'code': '159995', 'sector': '芯片', 'group': 'chips', 'risk_on': 1, 'keywords': ['芯片', '半导体', '存储', '封测']},
    'sh515980': {'name': '人工智能ETF', 'code': '515980', 'sector': 'AI算力', 'group': 'ai', 'risk_on': 1, 'keywords': ['AI', '人工智能', '算力', '大模型', '智能']},
    'sz159592': {'name': '卫星产业ETF', 'code': '159592', 'sector': '商业航天', 'group': 'aerospace', 'risk_on': 1, 'keywords': ['航天', '卫星', '商业航天', '火箭']},
    'sh515120': {'name': '创新药ETF', 'code': '515120', 'sector': '创新药', 'group': 'healthcare', 'risk_on': 1, 'keywords': ['医药', '创新药', '医疗', '生物', '健康']},
    'sh512170': {'name': '医疗ETF', 'code': '512170', 'sector': '医疗', 'group': 'healthcare', 'risk_on': 1, 'keywords': ['医疗', '医药', '器械', '生物']},
    'sh516160': {'name': '新能源ETF', 'code': '516160', 'sector': '新能源', 'group': 'new_energy', 'risk_on': 1, 'keywords': ['新能源', '光伏', '锂电', '储能', '充电']},
    'sh515790': {'name': '光伏ETF', 'code': '515790', 'sector': '光伏', 'group': 'new_energy', 'risk_on': 1, 'keywords': ['光伏', '太阳能', '硅料', '新能源']},
    'sh510150': {'name': '消费ETF', 'code': '510150', 'sector': '消费', 'group': 'consumption', 'risk_on': 1, 'keywords': ['消费', '零售', '食品', '白酒', '家电']},
    'sh512000': {'name': '券商ETF', 'code': '512000', 'sector': '券商', 'group': 'broker', 'risk_on': 1, 'keywords': ['券商', '证券', '金融', '牛市']},
    'sh512800': {'name': '银行ETF', 'code': '512800', 'sector': '银行', 'group': 'bank', 'risk_on': 1, 'keywords': ['银行', '息差', '金融']},
    'sh512200': {'name': '房地产ETF', 'code': '512200', 'sector': '房地产', 'group': 'property', 'risk_on': 1, 'keywords': ['房地产', '地产', '楼市', '住房']},
    'sh512660': {'name': '军工ETF', 'code': '512660', 'sector': '军工', 'group': 'defense', 'risk_on': 1, 'keywords': ['军工', '国防', '航天', '装备']},

    # 跨境
    'sh513050': {'name': '中概互联网ETF', 'code': '513050', 'sector': '中概互联网', 'group': 'hk_tech', 'risk_on': 1, 'keywords': ['中概', '互联网', '平台经济']},
    'sh513180': {'name': '恒生科技ETF', 'code': '513180', 'sector': '港股科技', 'group': 'hk_tech', 'risk_on': 1, 'keywords': ['恒生科技', '港股科技', '港股']},
    'sh513100': {'name': '纳指ETF', 'code': '513100', 'sector': '纳斯达克', 'group': 'us_equity', 'risk_on': 1, 'keywords': ['纳斯达克', '美股科技', '美股']},
    'sh513500': {'name': '标普500ETF', 'code': '513500', 'sector': '标普500', 'group': 'us_equity', 'risk_on': 1, 'keywords': ['标普500', '美国经济', '美股']},

    # 防守资产
    'sh518880': {'name': '黄金ETF', 'code': '518880', 'sector': '黄金', 'group': 'gold', 'risk_on': -1, 'keywords': ['黄金', '贵金属', '避险']},
    'sh511010': {'name': '国债ETF', 'code': '511010', 'sector': '国债', 'group': 'bond', 'risk_on': -1, 'keywords': ['国债', '利率', '降息', '债券']},
    'sh511260': {'name': '十年国债ETF', 'code': '511260', 'sector': '长债', 'group': 'bond', 'risk_on': -1, 'keywords': ['十年国债', '长债', '利率', '债券']},
    'sh511880': {'name': '货币ETF', 'code': '511880', 'sector': '现金', 'group': 'cash', 'risk_on': 0, 'keywords': ['货币基金', '现金', '流动性']},
}

SECTOR_ETF_MAP = {v['code']: {k: x for k, x in v.items() if k != 'code'} for v in ETF_UNIVERSE.values()}
