# 🧪 Training Deep-Dive: AI kaise sikhta hai?

Chalo ab thoda "Technical" hokar samajhte hain ki training actually hoti kaise hai. Is project mein do alag-alag AI models hain, aur dono ke sikhne ka tareeka bilkul alag hai.

---

## 1. YOLOv8: Gaadiyon ko Pehchan-na (Object Detection)

YOLO (You Only Look Once) ko hum **Supervised Learning** ke zariye sikhate hain. Iska matlab hai hum use "Answer Key" ke saath photos dikhate hain.

### Training Steps:
1.  **Collection:** Hum hazaro traffic photos jama karte hain (Roboflow ya UA-DETRAC se).
2.  **Labeling:** Har photo mein hum ek box banate hain aur batate hain ki "Ye Car hai", "Ye Bus hai", "Ye Ambulance hai". Ise *Annotation* kehte hain.
3.  **Feeding:** Hum computer ko photo dikhate hain. Computer guess karta hai. Agar guess galat hota hai, toh hum use batate hain, "Nahi, ye bus nahi, truck hai!".
4.  **Model File:** Lakhon baar practice karne ke baad, computer ek file banata hai jiska naam hota hai `yolo_traffic.pt`. Ye file ab gaadiyon ko pehchanne mein expert hai.

**Aap kya kar sakte hain?**
Agar aapke paas apni city ka video hai, toh aap uske frames nikaal kar Roboflow par label kar sakte hain aur firse `yolov8 train` command se apna khud ka model bana sakte hain.

---

## 2. DQN: Traffic Lights Manage Karna (Reinforcement Learning)

DQN (Deep Q-Network) ko hum **Reinforcement Learning** ke zariye sikhate hain. Ye "Trial and Error" (galti karke sikhna) par chalta hai.

### Training Steps (The Game Loop):
Isme koi "Photos" nahi hoti. Isme ek **Environment** hota hai (jo aapki `env.py` file mein hai).

1.  **State (Mahaul):** AI dekhta hai ki kis lane mein kitni gaadiyan hain aur kya koi ambulance khadi hai?
2.  **Action (Kaam):** AI faisla leta hai, "Chalo, North lane ko Green kar dete hain".
3.  **Reward (Inaam ya Saza):** 
    *   Agar gaadiyan jaldi nikal gayi, toh AI ko `+10` points milte hain.
    *   Agar gaadiyan khadi rahi aur wait time badha, toh AI ko `-1` point (Saza) milti hai.
    *   Agar **Ambulance** wait kar rahi hai, toh AI ko bahut badi saza (`-5` points per second) milti hai!
4.  **Learning:** AI baar-baar ye "game" khelta hai (hazaaron baar). Wo samajh jata hai ki zyada points lene ke liye use Ambulance ko pehle nikalna hoga aur bheed wali lane ko pehle kholna hoga.

### Training Command:
Aap is command se training shuru kar sakte hain:
`python -m backend.training.train_dqn`

---

## 3. Dataset ka use kaise karein?

Agar aap online dataset (jaise UA-DETRAC) use karna chahte hain:
1.  **Download:** Dataset ko download karein.
2.  **Convert:** Use YOLO format (`.txt` files) mein convert karein.
3.  **Path:** `backend/training/train_supervised.py` mein dataset ka path dein.
4.  **Train:** `python -m backend.training.train_supervised` chala dein.

## 4. Kya AI "Rules" (Constraints) Follow Karega? 🚦

Ye ek bahut important sawal hai! Teacher ke saath discuss kiye gaye constraints (jaise: "Kam se kam 10 second green hona chahiye") AI tabhi follow karega jab:

1.  **Environment mein Rules hon:** Agar hum `env.py` mein ye likh dein ki "Switch tabhi hoga jab 10 second pure ho jayein", toh AI ke paas koi aur option nahi rahega.
2.  **Rewards mein Saza ho:** Agar AI 10 second se pehle light badalta hai, toh hum uske points kaat lein (`-50` points!). Isse wo darr ke maare rules follow karega.

### Current Status:
*   **Rule-based Controller:** Isme `MIN_GREEN` (8s) aur `YELLOW_TIME` (5s) pehle se hardcoded hain. Ye hamesha rules follow karta hai.
*   **AI (DQN) Controller:** Isse humein sikhana padta hai. Agar aapka AI jaldi-jaldi lights badal raha hai (flickering), toh iska matlab humein uske dimaag mein ye rules "Reward" ke zariye daalne honge.

**Tip:** Agar aapke teacher ne koi specific rules diye hain, toh mujhe batayein, hum unhe `backend/ai/rl/env.py` mein add kar sakte hain!

**Summary:** 
- **YOLO** ko "Photos" chahiye (Supervised). 
- **DQN** ko "Practise" chahiye (RL).

Aap is project mein dono cheezein customize kar sakte hain!
