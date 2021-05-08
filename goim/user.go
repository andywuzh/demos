package main

import (
	"net"
	"strings"
)

type User struct {
	Name string
	Addr string
	C    chan string
	conn net.Conn

	server *Server
}

func NewUser(conn net.Conn, server *Server) *User {
	userAddr := conn.RemoteAddr().String()

	user := &User{
		Name:   userAddr,
		Addr:   userAddr,
		C:      make(chan string),
		conn:   conn,
		server: server,
	}

	go user.ListenMessage()

	return user
}

func (u *User) ListenMessage() {
	for {
		msg := <-u.C

		u.conn.Write([]byte(msg + "\n"))
	}
}

func (u *User) Online() {
	u.server.mapLock.Lock()
	u.server.OnlineMap[u.Name] = u
	u.server.mapLock.Unlock()

	u.server.BroadCast(u, "已上线")
}

func (u *User) Offline() {
	u.server.mapLock.Lock()
	delete(u.server.OnlineMap, u.Name)
	u.server.mapLock.Unlock()

	u.server.BroadCast(u, "已下线")
}

func (u *User) SendMsg(msg string) {
	u.conn.Write([]byte(msg))
}

func (u *User) DoMessage(msg string) {
	if msg == "who" {
		u.server.mapLock.Lock()
		for _, user := range u.server.OnlineMap {
			u.SendMsg("[" + user.Addr + "]" + user.Name + ":" + "当前在线\n")
		}
		u.server.mapLock.Unlock()
	} else if len(msg) > 7 && msg[:7] == "rename|" {
		newName := strings.Split(msg, "|")[1]
		if _, ok := u.server.OnlineMap[newName]; ok {
			u.SendMsg("当前用户名已被使用\n")
		} else {
			u.server.mapLock.Lock()
			delete(u.server.OnlineMap, u.Name)

			u.Name = newName
			u.server.OnlineMap[newName] = u

			u.server.mapLock.Unlock()
			u.SendMsg("更新名称成功\n")
		}
	} else if len(msg) > 4 && msg[:3] == "to|" {
		toName := strings.Split(msg, "|")[1]
		if toName == "" {
			u.SendMsg("消息格式不正确, 请使用\"to|张三|你好啊\"格式\n")
			return
		}

		toUser, ok := u.server.OnlineMap[toName]
		if !ok {
			u.SendMsg("该用户名不存在\n")
			return
		}

		toMsg := strings.Split(msg, "|")[2]
		toUser.SendMsg(toMsg)
	} else {
		u.server.BroadCast(u, msg)
	}
}
