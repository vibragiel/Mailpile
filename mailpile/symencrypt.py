import os
import sys
import random
from hashlib import sha512
from subprocess import Popen, PIPE
from datetime import datetime

def genkey(secret, salt):
    """
    Generate keys for files based on host key and filename. 
    Nice utility, Bob!
    """
    h = sha512()
    h.update(":%s:%s:" % (secret, salt))
    return h.hexdigest()


class SymmetricEncrypter:
    """
    Symmetric encryption/decryption. Currently wraps OpenSSL's command line.
    """

    def __init__(self, secret=None):
        self.available = None
        self.binary = 'openssl'
        self.handles = {}
        self.pipes = {}
        self.fds = ["stdout", "stderr"]
        self.errors = []
        self.statuscallbacks = {}
        self.defaultcipher = "aes-256-gcm"
        self.beginblock = "-----BEGIN MAILPILE ENCRYPTED DATA-----"
        self.endblock = "-----END MAILPILE ENCRYPTED DATA-----"
        self.secret = secret

    def run(self, args=[], output=None, debug=False):
        self.pipes = {}
        args.insert(0, self.binary)

        if debug: print "Running openssl as: %s" % " ".join(args)

        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        self.handles["stdout"] = proc.stdout
        self.handles["stderr"] = proc.stderr
        self.handles["stdin"] = proc.stdin

        if output:
            self.handles["stdin"].write(output)
            self.handles["stdin"].close()

        retvals = dict([(fd, "") for fd in self.fds])
        while True:
            proc.poll()
            for fd in self.fds:
                try:
                    buf = self.handles[fd].read()
                except IOError:
                    continue
                if buf == "":
                    continue
                retvals[fd] += buf
            if proc.returncode is not None:
                break

        return proc.returncode, retvals


    def encrypt(self, data, cipher=None):
        # TODO: Make keys get passed through files or environment
        if not cipher:
            cipher = self.defaultcipher
        salt = sha512(str(random.getrandbits(512))).hexdigest()[:32]
        enckey = genkey(self.secret, salt)
        params = ["enc", "-e", "-a", "-%s" % cipher, 
                  "-pass", "pass:%s" % enckey,
                 ]
        retval, res = self.run(params, output=data)
        ret = "%s\ncipher: %s\nsalt: %s\n\n%s\n%s" % (
            self.beginblock, cipher, salt, res["stdout"], self.endblock)
        return ret


    def decrypt(self, data):
        # TODO: Make keys get passed through files or environment
        cipher = self.defaultcipher
        salt = None

        try:
            head, enc, tail = data.split("\n\n")
            head = head.split("\n")
        except:
            head, enc, tail = data.split("\r\n\r\n")
            head = head.split("\r\n")

        if (head[0].strip() == self.beginblock
                and tail.strip() == self.endblock):
            del(head[0])
            while head:
                line = head.pop(0)
                if line == "":
                    break
                try:
                    key, value = line.split(": ")
                except:
                    raise ValueError("Message contained invalid parameter.")

                if key == "cipher":
                    cipher = value.strip()
                elif key == "salt":
                    salt = value.strip()
                else:
                    raise ValueError("Message contained invalid parameter.")
        else:
            raise ValueError("Not a valid OpenSSL encrypted block.")

        if not salt:
            raise ValueError("Encryption salt not known.")

        enckey = genkey(self.secret, salt)
        params = ["enc", "-d", "-a", "-%s" % cipher, 
                  "-pass", "pass:%s" % enckey,
                 ]
        retval, res = self.run(params, output=enc)
        return res["stdout"]


class EncryptedFile(object):
    def __init__(self, filename, secret, mode="w"):
        self.encrypter = SymmetricEncrypter(secret)
        self.filename = filename
        self.fd = open(fd, mode)

    def write(self, data):
        enc = self.encrypter.encrypt(data)
        self.fd.write(enc)

    def read(self):
        enc = self.fd.readlines()
        data = self.encrypter.decrypt(enc)

    def close(self):
        self.fd.close()


if __name__ == "__main__":
    s = SymmetricEncrypter("d3944bfea1e882dfc2e4878fa8905c6a2c")
    teststr = "Hello! This is a longish thing."
    testpass = "kukalabbi"
    if teststr == s.decrypt(s.encrypt(teststr)):
        print "Basic decryption worked"
    else:
        print "Encryption test failed"

    print "Example encrypted format:"
    print s.encrypt(teststr)

    t0 = datetime.now()
    enc = s.encrypt(teststr)
    print "Speed test:"
    for i in range(10000):
        s.decrypt(enc)
        if i % 100 == 0:
            print "\r %-3d%% %s>" % (int(i / 100.0), "-" * (i//200)),
            sys.stdout.flush()
    t1 = datetime.now()
    print "\n10000 decrypt operations took %s" % (t1-t0)
