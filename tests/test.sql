create or replace procedure ZTC_JURUI_KHZF_PRC is
begin
  ZTC_SQLZZ('
  INSERT INTO ztc_jurui_khjl_tmp2
  SELECT to_char(sysdate-1,''yyyymmdd'') as 账期,''累计已走访客户经理数'' as tp,2 as xh,
  count(case when a.行政架构下的政企承包支局名称 = ''市数字政府行客支局'' 
         then 1 else null end) 创新中心
  FROM ztc_jurui_khjl_tmp1 a
  WHERE TO_CHAR(to_date(a.创建时间,''yyyy-mm-dd hh24:mi:ss''),''YYYYMMdd'') >= 202008
  ');
end ZTC_JURUI_KHZF_PRC;