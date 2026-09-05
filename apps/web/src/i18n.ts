import i18n from 'i18next'; import {initReactI18next} from 'react-i18next';
import en from './locales/en/translation.json'; import sw from './locales/sw/translation.json';
i18n.use(initReactI18next).init({resources:{en:{translation:en},sw:{translation:sw}},lng:localStorage.getItem('launder-language')||'en',fallbackLng:'en',interpolation:{escapeValue:false}});
i18n.on('languageChanged',lng=>localStorage.setItem('launder-language',lng)); export default i18n;
export const money=(n:number)=>new Intl.NumberFormat(i18n.language==='sw'?'sw-TZ':'en-TZ',{style:'currency',currency:'TZS',maximumFractionDigits:0}).format(n);
