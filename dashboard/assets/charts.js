(function(){
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var green = style.getPropertyValue('--green').trim();
  var red = style.getPropertyValue('--accent2').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var gold = style.getPropertyValue('--gold').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var warn = style.getPropertyValue('--warn').trim() || gold;
  var positive = style.getPropertyValue('--positive').trim() || green;
  var negative = style.getPropertyValue('--negative').trim() || red;
  var charts = [];

  function makeChart(id, option){
    var el = document.getElementById(id);
    if(!el) return;
    var c = echarts.init(el, null, {renderer:'svg'});
    c.setOption(option);
    charts.push(c);
  }

  // 1. 累计收益率走势
  makeChart('chart-cum', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    legend:{data:['模型累计','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:["01-06", "01-07", "01-08", "01-09", "01-12", "01-13", "01-14", "01-15", "01-16", "01-19", "01-20", "01-21", "01-22", "01-23", "01-26", "01-27", "01-28", "01-29", "01-30", "02-02", "02-03", "02-04", "02-05", "02-10", "02-13", "02-26", "03-03", "03-06", "03-11", "03-16", "03-19", "03-20", "03-23", "03-24", "03-25", "03-26", "03-27", "03-30", "04-02", "04-08", "04-09", "04-14", "04-17", "04-22", "04-23", "04-28", "04-29", "05-07", "05-12", "05-15", "05-18", "05-19", "05-20", "05-21", "05-22", "05-25", "05-26", "05-29", "06-03", "06-08", "06-11", "06-12", "06-15", "06-18", "06-24", "06-25", "06-30", "07-03", "07-08", "07-13", "07-14", "07-15", "07-20", "07-21", "07-24", "07-29", "08-03"],axisLabel:{color:muted,fontSize:10,interval:9},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型累计',type:'line',data:[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.08, -0.08, 0.32, 0.61, 0.04, -0.0, -0.49, -0.83, -0.83, -0.83, -0.83, -0.83, -0.83, -0.83, -0.83, 0.32, -0.05, -0.05, 0.22, 0.96, 1.51, 1.51, 0.89, 0.89, 0.69, 2.33, 0.71, 0.71, 0.71, 0.71, 0.71, 0.71, 0.71, 0.71, 0.13, -0.34, -0.63, -0.87, -0.87, -0.87, -0.71, 0.35, 0.35, 1.65, 1.77, 1.57, 1.56, 1.56, 1.56, 1.18, 1.18, 1.31, 1.12, 1.14, 1.16],smooth:true,lineStyle:{color:green,width:2},itemStyle:{color:green},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(52,199,89,0.15)'},{offset:1,color:'rgba(52,199,89,0)'}]}}},
      {name:'沪深300',type:'line',data:[1.46, 1.06, 0.54, 1.13, 1.55, 1.01, 0.38, 0.93, -0.03, -0.01, -0.24, 0.2, -0.09, -0.68, -0.68, -0.73, -0.73, 0.2, -0.32, -2.03, -1.52, -0.33, 0.67, 0.54, 1.31, 1.06, -0.78, 0.15, -0.05, -0.32, -0.8, -1.28, -3.44, -3.08, -2.33, -3.39, -2.08, -0.47, -2.13, -0.29, 1.43, 2.87, 3.69, 4.76, 3.97, 4.06, 6.85, 8.1, 7.41, 6.26, 6.2, 6.73, 7.27, 5.45, 6.16, 7.33, 7.73, 7.53, 5.61, 5.48, 5.17, 5.33, 7.39, 7.37, 8.14, 7.86, 5.9, 5.82, 5.67, 4.46, 6.42, 1.45, 1.89, 4.24, 1.65, 2.28, 1.74],smooth:true,lineStyle:{color:accent,width:1.5,type:'dashed'},itemStyle:{color:accent}}
    ]
  });

  // 2. 月度收益对比
  makeChart('chart-month', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){
      var s=p[0].name+'月<br/>';
      p.forEach(function(i){s+=i.marker+i.seriesName+':'+i.value+'%<br/>'});
      return s;
    }},
    legend:{data:['模型','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:["01", "02", "03", "04", "05", "06", "07", "08"],axisLabel:{color:muted,fontSize:11},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[0.0, 0.61, -0.29, 0.37, -1.03, 2.11, -0.63, 0.02],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.32, 1.38, -1.53, 7.32, 0.68, -1.63, -3.62, -0.54],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.6)':'rgba(255,59,48,0.6)'}},barWidth:'30%'}
    ]
  });

  // 3. ETF 胜率分布
  makeChart('chart-etf', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){return p[0].name+':'+p[0].value+'%'}},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["中证500ETF", "光伏ETF", "军工ETF", "创新药ETF", "券商ETF", "医疗ETF", "十年国债ETF", "卫星产业ETF", "恒生科技ETF", "房地产ETF", "新能源ETF", "标普500ETF", "消费ETF", "红利ETF", "芯片ETF", "银行ETF", "黄金ETF"],axisLabel:{color:muted,fontSize:9,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',max:100,axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[0.0, 100.0, 50.0, 66.7, 100.0, 33.3, 100.0, 50.0, 0.0, 66.7, 66.7, 50.0, 0.0, 66.7, 100.0, 0.0, 0.0],
      itemStyle:{color:function(p){return p.value>=55?green:p.value>=45?gold:red}},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}%',color:muted,fontSize:9}
    }]
  });

  // 4. 近15日每日收益对比
  makeChart('chart-rec', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    legend:{data:['模型','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:["06-15", "06-18", "06-24", "06-25", "06-30", "07-03", "07-08", "07-13", "07-14", "07-15", "07-20", "07-21", "07-24", "07-29", "08-03"],axisLabel:{color:muted,fontSize:10,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[0.16, 1.06, 0.0, 1.3, 0.12, -0.21, -0.01, 0.0, 0.0, -0.38, 0.0, 0.13, -0.19, 0.02, 0.02],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[2.06, -0.02, 0.77, -0.28, -1.96, -0.08, -0.14, -1.21, 1.96, -4.97, 0.43, 2.35, -2.59, 0.63, -0.54],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.5)':'rgba(255,59,48,0.5)'}},barWidth:'30%'}
    ]
  });

  // 5. 因素重要性
  makeChart('chart-imp', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["sentiment_score", "bullish_count", "bearish_count", "prev_change_pct", "prev_volume_ratio", "prev_intraday_return", "sector_mentioned", "sector_mention_count", "hs300_mom_5d", "vol_10d", "retail_sentiment", "rzjme_yi", "sentiment_divergence", "behavior_momentum", "flow_proxy", "acceleration", "crowding", "withdrawal_risk", "early_entry", "news_surprise", "market_breadth", "external_signal", "external_news_count", "news_price_gap", "news_flow_gap"],axisLabel:{color:muted,fontSize:9,rotate:25},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      itemStyle:{color:gold},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}',color:muted,fontSize:9}
    }]
  });

  window.addEventListener('resize', function(){
    charts.forEach(function(c){ c.resize(); });
  });
})();
