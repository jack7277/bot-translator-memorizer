Бот переводит слова с англ на русский и по кривой забывания напоминает их в телеграме 

@MemNa_Bot


#Период напоминаний:#

r1 = 12 или 15 часов дня

r2 = r1 + timedelta(seconds=5)

r3 = r1 + timedelta(minutes=60)

r4 = r3 + timedelta(hours=5)

r5 = r1 + timedelta(days=1)

r6 = r5 + timedelta(days=1)

r7 = r6 + timedelta(days=1)

r8 = r7 + timedelta(days=5)

r9 = r8 + timedelta(weeks=2)

r10 = r9 + timedelta(weeks=4)

r11 = r10 + timedelta(weeks=10)

r12 = r11 + timedelta(weeks=16)