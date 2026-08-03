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
    xAxis:{type:'category',data:["01-03", "01-06", "01-07", "01-08", "01-09", "01-10", "01-13", "01-14", "01-15", "01-16", "01-17", "01-20", "01-21", "01-22", "01-23", "01-24", "01-27", "02-05", "02-06", "02-07", "02-10", "02-13", "02-18", "02-21", "02-26", "03-03", "03-04", "03-05", "03-10", "03-13", "03-18", "03-21", "03-26", "03-31", "04-03", "04-09", "04-10", "04-11", "04-14", "04-15", "04-18", "04-23", "04-24", "04-29", "05-07", "05-12", "05-15", "05-20", "05-23", "05-28", "06-03", "06-04", "06-09", "06-12", "06-17", "06-18", "06-19", "06-20", "06-23", "06-24", "06-27", "07-02", "07-07", "07-10", "07-15", "07-18", "07-23", "07-28", "07-31", "08-01", "08-06", "08-11", "08-14", "08-19", "08-22", "08-27", "09-01", "09-04", "09-09", "09-12", "09-17", "09-22", "09-23", "09-24", "09-25", "09-30", "10-13", "10-16", "10-21", "10-24", "10-29", "11-03", "11-04", "11-07", "11-12", "11-17", "11-20", "11-21", "11-24", "11-25", "11-26", "12-01", "12-04", "12-05", "12-10", "12-15", "12-16", "12-19", "12-24", "12-29", "01-05", "01-06", "01-09", "01-14", "01-19", "01-20", "01-21", "01-22", "01-27", "01-30", "02-04", "02-05", "02-10", "02-13", "02-26", "03-03", "03-06", "03-11", "03-16", "03-19", "03-20", "03-23", "03-24", "03-27", "03-30", "04-02", "04-08", "04-09", "04-14", "04-17", "04-22", "04-27", "04-28", "04-29", "05-07", "05-12", "05-15", "05-18", "05-19", "05-20", "05-21", "05-22", "05-25", "05-26", "05-29", "06-03", "06-08", "06-09", "06-12", "06-15", "06-18", "06-24", "06-25", "06-30", "07-03", "07-08", "07-13", "07-14", "07-15", "07-20", "07-23", "07-28", "07-31"],axisLabel:{color:muted,fontSize:10,interval:9},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型累计',type:'line',data:[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.14, 0.37, 0.27, 0.2, -0.21, -0.21, -0.21, -0.02, 0.26, 0.35, 0.22, 0.14, -0.23, -0.09, -0.82, -0.82, -0.82, -0.82, -0.82, -1.31, -1.23, -1.23, -1.2, -0.82, -1.7, -1.29, -2.45, -1.89, -1.99, -1.99, -1.99, -2.04, -1.99, -2.39, -2.39, -2.39, -2.39, -2.39, -2.39, -2.01, -1.92, -1.84, -1.87, -1.6, -0.88, -0.25, 0.06, 0.09, 0.09, 0.07, 0.09, 0.37, 2.02, 1.82, 2.94, 3.27, 3.23, 3.39, 3.6, 3.84, 3.93, 3.93, 3.93, 3.93, 4.25, 4.1, 4.48, 4.54, 4.82, 5.36, 4.64, 4.64, 5.21, 5.44, 5.49, 5.22, 5.22, 5.22, 5.22, 5.22, 5.38, 5.33, 5.33, 5.56, 5.59, 5.59, 5.67, 5.58, 6.09, 5.35, 5.35, 5.25, 5.35, 5.12, 5.12, 5.12, 5.12, 4.93, 5.8, 5.0, 5.0, 5.0, 4.72, 5.12, 5.45, 4.92, 4.87, 4.82, 3.97, 3.97, 3.97, 3.97, 3.97, 3.97, 4.86, 4.51, 4.51, 5.22, 6.0, 6.22, 6.28, 6.28, 6.28, 5.98, 7.85, 6.82, 6.82, 6.82, 6.82, 6.82, 6.82, 6.82, 6.82, 6.21, 5.71, 5.09, 5.09, 5.07, 5.07, 5.18, 6.23, 6.23, 7.69, 7.65, 7.47, 7.81, 7.81, 7.81, 7.56, 7.56, 7.29, 6.75, 6.76],smooth:true,lineStyle:{color:green,width:2},itemStyle:{color:green},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(52,199,89,0.15)'},{offset:1,color:'rgba(52,199,89,0)'}]}}},
      {name:'沪深300',type:'line',data:[-1.08, -1.41, -0.45, -0.34, -0.26, -1.41, -1.21, 1.31, 0.96, 0.66, 1.29, 1.18, 0.78, -0.03, -0.51, 0.57, -0.21, -1.36, -0.06, 1.42, 2.08, 2.93, 2.56, 2.27, 1.38, 1.01, 1.47, 3.03, 2.72, 4.55, 3.73, 2.85, 2.4, 1.74, -4.09, -2.05, -1.72, -0.88, -1.19, -0.66, -0.09, -0.36, -0.52, 0.27, 0.14, 2.32, 0.88, 1.76, 0.02, 0.34, 0.64, 1.36, 1.76, 1.54, 1.49, 1.52, 0.86, 1.02, 1.6, 3.99, 3.94, 5.15, 5.64, 6.48, 6.99, 9.32, 9.3, 10.01, 8.4, 9.27, 9.32, 11.29, 12.78, 14.02, 17.92, 19.28, 17.99, 18.19, 20.79, 19.87, 19.62, 19.96, 19.85, 21.32, 22.75, 22.43, 24.84, 23.77, 25.03, 26.63, 25.48, 25.72, 26.69, 26.11, 25.83, 25.11, 24.07, 22.28, 21.78, 22.17, 22.95, 22.93, 23.12, 24.27, 24.14, 23.99, 24.16, 25.48, 26.43, 25.85, 27.16, 27.44, 28.26, 27.49, 27.51, 27.27, 27.72, 27.11, 28.3, 26.78, 27.96, 28.96, 28.84, 29.6, 29.35, 27.51, 28.44, 28.25, 27.97, 27.49, 27.01, 24.85, 25.41, 26.71, 28.33, 26.67, 28.51, 30.23, 31.66, 32.49, 32.95, 32.87, 32.95, 35.75, 36.99, 36.31, 35.15, 35.09, 35.63, 36.16, 34.35, 35.05, 36.22, 36.63, 36.42, 34.5, 33.44, 33.16, 33.33, 35.39, 35.37, 36.14, 35.86, 33.9, 33.81, 33.67, 32.46, 34.42, 29.45, 32.37, 31.93, 30.11, 28.38],smooth:true,lineStyle:{color:accent,width:1.5,type:'dashed'},itemStyle:{color:accent}}
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
    xAxis:{type:'category',data:["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "01", "02", "03", "04", "05", "06", "07"],axisLabel:{color:muted,fontSize:11},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[0.0, -0.21, 0.12, -0.73, -1.17, 0.06, 2.02, 3.18, 0.83, 0.55, 0.74, -0.03, -0.35, 0.45, -0.59, 1.12, -0.27, 1.95, -0.89],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.21, 1.59, 0.36, -1.48, 0.07, 3.59, 4.46, 10.89, 3.15, 3.05, -2.53, 2.91, 0.92, 2.57, -1.02, 7.42, 0.68, -2.53, -5.51],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.6)':'rgba(255,59,48,0.6)'}},barWidth:'30%'}
    ]
  });

  // 3. ETF 胜率分布
  makeChart('chart-etf', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){return p[0].name+':'+p[0].value+'%'}},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["上证50ETF", "中概互联网ETF", "中证1000ETF", "人工智能ETF", "光伏ETF", "军工ETF", "创新药ETF", "券商ETF", "医疗ETF", "十年国债ETF", "半导体ETF", "国债ETF", "恒生科技ETF", "房地产ETF", "新能源ETF", "标普500ETF", "沪深300ETF", "消费ETF", "红利ETF", "红利低波ETF", "纳指ETF", "芯片ETF", "银行ETF", "黄金ETF"],axisLabel:{color:muted,fontSize:9,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',max:100,axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[33.3, 100.0, 100.0, 0.0, 50.0, 33.3, 50.0, 80.0, 33.3, 100.0, 100.0, 66.7, 0.0, 0.0, 33.3, 100.0, 51.4, 50.0, 66.7, 100.0, 0.0, 100.0, 50.0, 50.0],
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
    xAxis:{type:'category',data:["06-12", "06-15", "06-18", "06-24", "06-25", "06-30", "07-03", "07-08", "07-13", "07-14", "07-15", "07-20", "07-23", "07-28", "07-31"],axisLabel:{color:muted,fontSize:10,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[0.0, 0.11, 1.05, 0.0, 1.46, -0.04, -0.19, 0.34, 0.0, 0.0, -0.25, 0.0, -0.28, -0.54, 0.01],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[0.17, 2.06, -0.02, 0.77, -0.28, -1.96, -0.08, -0.14, -1.21, 1.96, -4.97, 2.92, -0.44, -1.81, -1.73],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.5)':'rgba(255,59,48,0.5)'}},barWidth:'30%'}
    ]
  });

  // 5. 因素重要性
  makeChart('chart-imp', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["withdrawal_risk", "prev_intraday_return", "sentiment_score", "bullish_count", "bearish_count", "prev_change_pct", "prev_volume_ratio", "sector_mentioned", "sector_mention_count", "hs300_mom_5d", "vol_10d", "retail_sentiment", "rzjme_yi", "sentiment_divergence", "behavior_momentum", "flow_proxy", "acceleration", "crowding", "early_entry", "news_surprise", "market_breadth", "external_signal", "external_news_count", "news_price_gap", "news_flow_gap", "share_flow_signal"],axisLabel:{color:muted,fontSize:9,rotate:25},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[0.014005, 0.005248, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      itemStyle:{color:gold},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}',color:muted,fontSize:9}
    }]
  });

  window.addEventListener('resize', function(){
    charts.forEach(function(c){ c.resize(); });
  });
})();
