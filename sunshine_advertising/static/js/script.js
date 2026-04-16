/* Sunshine Advertising - Interactions */

const translations = {
    en: {
        brand: "SUNSHINE",
        subtitle: "ADVERTISING",
        nav_home: "Home",
        nav_services: "Services",
        nav_fleet: "Our Fleet",
        nav_contact: "Contact",
        hero_title: "172-LED VANS Available on a Single Roof",
        hero_p: "The most effective way to reach maximum people in the shortest time. Your partner in digital marketing and campaign success.",
        btn_book: "Book Now",
        services_title: "Our Specialized Services",
        service_1_h: "Video Documentaries",
        service_1_p: "Professional video storytelling and campaign documentaries to engage your audience.",
        service_2_h: "Audio & Campaign Songs",
        service_2_p: "Catchy audio clips and campaign songs designed for loud and clear impact.",
        service_3_h: "Bulk Messaging",
        service_3_p: "Reach thousands instantly via Bulk SMS, Voice Calls, and WhatsApp.",
        service_4_h: "Digital Marketing",
        service_4_p: "End-to-end digital strategy to boost your presence and winning chances.",
        fleet_title: "Our Massive Fleet",
        fleet_p: "With 172 high-quality LED Vans and Walls, we cover Dharashiv and beyond for any event scale.",
        footer_bot: "Nagarsevak Pravin Mali Help Line — A Citizen Initiative by Sunshine Advertising",
        address: "Jijau Chowk, Barshi Naka, Dharashiv (Osmanabad) - 413501",
        phone: "Contact: 9277 11 55 11 / 7030 811 811",
        follow: "Follow us on"
    },
    mr: {
        brand: "सनशाईन",
        subtitle: "ॲडव्हर्टायझिंग",
        nav_home: "मुख्यपृष्ठ",
        nav_services: "सेवा",
        nav_fleet: "आमचा ताफा",
        nav_contact: "संपर्क",
        hero_title: "१७२-LED VAN एकाच छताखाली उपलब्ध",
        hero_p: "कमीत कमी वेळेत, जास्तीत जास्त लोकांपर्यंत पोहोचण्याचे प्रभावी माध्यम. डिजिटल मार्केटिंग आणि प्रचारासाठी तुमची विश्वसनीय साथ.",
        btn_book: "आत्ताच बुक करा",
        services_title: "आमच्या विशेष सेवा",
        service_1_h: "व्हिडिओ डॉक्युमेंट्री",
        service_1_p: "तुमच्या कार्याची माहिती लोकांपर्यंत पोहोचवण्यासाठी प्रोफेशनल व्हिडिओ माहितीपट.",
        service_2_h: "ऑडिओ आणि प्रचार गीत",
        service_2_p: "प्रभावी ऑडिओ क्लिप्स आणि लोकांच्या मनात घर करणारी प्रचार गीते.",
        service_3_h: "बल्क मेसेजिंग",
        service_3_p: "बल्क एसएमएस, व्हॉईस कॉल आणि व्हॉट्सॲप मेसेजद्वारे हजारो लोकांपर्यंत त्वरित पोहोचा.",
        service_4_h: "डिजिटल मार्केटिंग",
        service_4_p: "तुमचा प्रभाव वाढवण्यासाठी आणि जिंकण्याची संधी अधिक भक्कम करण्यासाठी डिजिटल रणनीती.",
        fleet_title: "आमचा प्रचंड ताफा",
        fleet_p: "१७२ उच्च दर्जाच्या एलईडी व्हॅन्ससह, आम्ही धाराशिव आणि इतर भागात कोणत्याही स्तरावरील कार्यक्रमासाठी सज्ज आहोत.",
        footer_bot: "नगरसेवक प्रविण माळी हेल्पलाईन — सनशाईन ॲडव्हर्टायझिंगचा एक उपक्रम",
        address: "जिजाऊ चौक, बार्शी नाका, धाराशिव (उस्मानाबाद) - ४१३५०१",
        phone: "संपर्क: ९२७७ ११ ५५ ११ / ७०३० ८११ ८११",
        follow: "येथे फॉलो करा"
    }
};

let currentLang = 'mr'; // Default Marathi
let currentTheme = 'light';

function toggleLanguage() {
    currentLang = currentLang === 'en' ? 'mr' : 'en';
    document.getElementById('lang-btn').textContent = currentLang === 'en' ? 'मराठी' : 'English';
    updateContent();
}

function updateContent() {
    const langData = translations[currentLang];
    document.querySelectorAll('[data-key]').forEach(elem => {
        const key = elem.getAttribute('data-key');
        if (langData[key]) {
            elem.textContent = langData[key];
        }
    });
}

function toggleTheme() {
    currentTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.body.setAttribute('data-theme', currentTheme);
    document.getElementById('theme-icon').className = currentTheme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
}

// Initial update
window.onload = () => {
    updateContent();
};
