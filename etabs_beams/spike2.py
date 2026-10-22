import comtypes.client, time, collections
obj = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
m = obj.SapModel
r = m.FrameObj.GetAllFrames()
print("fields:", len(r), "ret=", r[-1])
n, names, props, stories = r[0], r[1], r[2], r[3]
# orientation counts
t=time.time(); cnt=collections.Counter(); beams=[]
for nm in names:
    o = m.FrameObj.GetDesignOrientation(nm)
    cnt[o[0]]+=1
    if o[0]==2: beams.append(nm)
print("orientation counts (1=col,2=beam,3=brace,4=null,5=other):", dict(cnt), "time %.2fs"%(time.time()-t))
print("stories sample:", sorted(set(stories))[:8], len(set(stories)))
cases = m.LoadCases.GetNameList(); combos = m.RespCombo.GetNameList()
print("cases:", cases[0], cases[1][:10], "| combos:", combos[0], combos[1][:10])
print("units enum ->", m.GetPresentUnits())
if beams:
    b = beams[0]; i = names.index(b)
    print("beam", b, props[i], stories[i], "pts", r[4][i], r[5][i], "len?", [round(x,3) for x in (r[6][i],r[7][i],r[8][i],r[9][i],r[10][i],r[11][i])])
    res = m.Results.Setup
    res.DeselectAllCasesAndCombosForOutput()
    pick = combos[1][0] if combos[0] else cases[1][0]
    print("pick", pick, "setcombo->", res.SetComboSelectedForOutput(pick) if combos[0] else res.SetCaseSelectedForOutput(pick))
    t=time.time(); f = m.Results.FrameForce(b, 0)   # ObjectElm=0
    print("FrameForce n=", f[0], "ret=", f[-1], "time %.3fs"%(time.time()-t))
    for k in range(min(f[0],6)):
        print(f[1][k], round(f[2][k],3), f[5][k], f[6][k], [round(f[j][k],2) for j in range(8,14)])
