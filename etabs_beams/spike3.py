import comtypes.client, time
obj = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
m = obj.SapModel
m.Results.Setup.DeselectAllCasesAndCombosForOutput(); m.Results.Setup.SetComboSelectedForOutput('900.GS')
for b in ('2','3','4'):
    t=time.time(); f=m.Results.FrameForce(b,0); print("FrameForce",b,f[0],"%.3fs"%(time.time()-t))
db = m.DatabaseTables
t=time.time(); tb = db.GetAvailableTables(); print("tables ret", tb[-1], len(tb[1]))
cand=[k for k in tb[1] if 'Beam' in k and 'Force' in k or k.startswith('Element Forces')]
print(cand)
key='Element Forces - Beams'
fl = db.GetAllFieldsInTable(key); print("fields:", fl[-1], fl[3] if len(fl)>3 else fl)
print(db.SetLoadCombinationsSelectedForDisplay(['900.GS']), db.SetLoadCasesSelectedForDisplay([]))
t=time.time(); r=db.GetTableForDisplayArray(key, [''], 'All', 0, [], 0, [])
print("tbl ret", r[-1], "rows", r[3] if len(r)>3 else r[:5], "time %.2fs"%(time.time()-t))
print(r[2] if len(r)>2 else '')
d=r[4]; nf=len(r[2]); print([d[i] for i in range(nf*2)])
