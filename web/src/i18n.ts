// Locale seam: strings and number/date formatters stay outside protocol artifacts.
export const locale='ru-RU';
export const nav=[['/','Жизнь'],['/organism','Программы'],['/evolution','История'],['/lab','Испытания'],['/inventions','Открытия'],['/memory','Память'],['/science','Как проверяем'],['/about','О САМО']] as const;
export const condition:Record<string,string>={fixed:'Фиксированный предок',random:'Случайный поиск',gp:'Генетическое программирование',meta:'Изменяемый поиск',samo:'Полное САМО'};
export const change:Record<string,string>={modules:'Программы',search:'Стратегия поиска',dialect:'Семантика инструкций',memory:'Память',router:'Маршрутизация',architecture:'Состав модулей'};
export const family:Record<string,string>={balanced:'Смешанный набор (неполная оценка)',constant:'Постоянные',arithmetic:'Арифметические',periodic:'Периодические',recurrence:'Рекуррентные',switch:'Смена закона',random:'Случайный контроль',quadratic:'Квадратичные',xor:'XOR-процессы'};
export const status:Record<string,string>={completed:'Пилот завершён',sterile:'Размножение прекратилось',running:'Последняя запись: выполнялся',interrupted:'Прерван',failed:'Ошибка инфраструктуры',wall_limit:'Лимит времени',fuel_limit:'Лимит вычислений'};
export const pct=(v:number|undefined)=>v===undefined?'Нет измерения':new Intl.NumberFormat(locale,{style:'percent',maximumFractionDigits:1}).format(v);
export const num=(v:number)=>new Intl.NumberFormat(locale,{maximumFractionDigits:2}).format(v);
export const date=(v:string|null)=>v?new Intl.DateTimeFormat(locale,{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Krasnoyarsk'}).format(new Date(v)):'Наблюдений нет';
